# coding: utf-8
import os
import logging
import requests
from lxml import etree
from StringIO import StringIO
from datetime import datetime

from file_utils import delete_file_or_folder, write_file
from constants import XML_ERRORS_ROOT_PATH


ARTICLEMETA_ARTICLE_URL = "http://articlemeta.scielo.org/api/v1/article"


def get_xml_text(collection, code):
    url = "{}/?collection={}&code={}&format=xmlwos\n".format(
        ARTICLEMETA_ARTICLE_URL, collection, code
    )
    params = {"collection": collection, "code": code, "format": "xmlwos"}
    return requests.get(url, params=params, timeout=30).text


def remove_contrib_id(text):
    """Remove contributor IDs from XML."""
    if "</contrib-id>" not in text:
        return False, text

    p = text.find("<article")
    pref = text[:p]
    xml = text[p:]
    xmltree = etree.fromstring(xml)
    for contrib_id in xmltree.findall(".//contrib-id"):
        parent = contrib_id.getparent()
        parent.remove(contrib_id)
    return True, pref + etree.tostring(xmltree, encoding="utf-8").decode("utf-8")


class XML(object):
    """XML parsing and handling."""

    def __init__(self, textxml):
        self.parse_errors = []
        self.tree = None
        self.text = textxml
        try:
            self.tree = etree.fromstring(textxml)
        except etree.XMLSyntaxError as e:
            self.parse_errors.append(e.message)
        except Exception as e:
            logging.exception(e)
            self.parse_errors.append(f"Unable to load xml: {e} {str(type(e))}")

    @property
    def pretty_text(self):
        if self.tree is None:
            return self.text.replace("<", "\n<").replace("\n</", "</").strip()
        return etree.tostring(self.tree, encoding="utf-8", pretty_print=True)


class XMLValidatorWithSchema(object):
    """XML validator using schema."""

    def __init__(self, xsd_filename):
        self.xml_schema = xsd_filename

    @property
    def xml_schema(self):
        return self._xml_schema

    @xml_schema.setter
    def xml_schema(self, xsd_filename):
        try:
            with open(xsd_filename, "r") as str_schema:
                schema_doc = etree.parse(str_schema)
                self._xml_schema = etree.XMLSchema(schema_doc)
        except (IOError, ValueError, etree.XMLSchemaError) as e:
            logging.exception("xml_processing.XMLValidatorWithSchema.xml_schema", e)

    def validate(self, tree):
        if self.xml_schema is None:
            return "XMLSchema is not loaded"

        try:
            self.xml_schema.validate(tree)
        except etree.XMLSyntaxError as e:
            return e.message
        except Exception as e:
            logging.exception("xml_processing.XMLValidatorWithSchema.validate", e)

        try:
            self.xml_schema.assertValid(tree)
        except etree.DocumentInvalid as e:
            return e.message
        except Exception as e:
            logging.exception("xml_processing.XMLValidatorWithSchema.assertValid", e)


class ValidatedXML(object):
    """Validated XML wrapper."""

    def __init__(self, textxml):
        self._errors = []

        self.xml = XML(textxml)
        self.errors = self.xml.parse_errors

        self.xml = XML(self.xml.pretty_text)
        self.errors = self.xml.parse_errors

    @property
    def article(self):
        if self.xml is not None:
            return self.xml.tree.find("./article")

    @property
    def text(self):
        if self.xml is not None:
            return self.xml.text

    @property
    def errors(self):
        return self._errors

    @errors.setter
    def errors(self, messages):
        if messages is not None:
            if isinstance(messages, list):
                self._errors.extend(messages)
            else:
                self._errors.append(messages)

    def validate(self, validate_with_schema=None):
        if validate_with_schema is not None:
            self.errors = validate_with_schema.validate(self.xml.tree)

    def display(self, numbered_lines=False):
        if self.xml is not None:
            if numbered_lines:
                lines = self.xml.text.split("\n")
                nlines = len(lines)
                digits = len(str(nlines))
                return "\n".join(
                    [
                        "{}:{}".format(str(n).zfill(digits), line)
                        for n, line in zip(range(1, nlines), lines)
                    ]
                )
            return self.xml.text

    def get_report_content(self, numbered=False):
        now = datetime.now().isoformat()
        errors = "\n".join(self.errors)
        sep = "\n" * 2
        content = []
        xml = self.display(numbered)
        if numbered:
            content = [now, self.url, "ERRORS\n" + "=" * 6, errors, "-" * 30, xml]
        else:
            content = [xml, "-" * 30, now, self.url, "ERRORS\n" + "=" * 6, errors]
        return sep.join(content)


class ArticleReport(object):
    """Report for article XML validation."""

    def __init__(self, collection, code, xml_error_root_path):
        self.collection = collection
        self.code = code
        self.xml_error_root_path = xml_error_root_path
        self.report_filename = "{}/{}.err.txt".format(self.issn_path, self.code)
        self.url = "{}/?collection={}&code={}&format=xmlwos\n".format(
            ARTICLEMETA_ARTICLE_URL, self.collection, self.code
        )

    @property
    def issn_path(self):
        issn = self.code[1:10]
        path = "{}/{}/{}".format(self.xml_error_root_path, self.collection, issn)
        if not os.path.isdir(path):
            os.makedirs(path)
        return path

    def get_content(self, validated, numbered=False):
        now = datetime.now().isoformat()
        errors = "\n".join(validated.errors)
        sep = "\n" * 2
        content = []
        xml = validated.display(numbered)
        if numbered:
            content = [now, self.url, "ERRORS\n" + "=" * 6, errors, "-" * 30, xml]
        else:
            content = [xml, "-" * 30, now, self.url, "ERRORS\n" + "=" * 6, errors]
        return sep.join(content)

    def save(self, validated, numbered=False):
        if validated.errors is None or len(validated.errors) == 0:
            return delete_file_or_folder(self.report_filename)
        write_file(self.report_filename, self.get_content(validated, numbered))


class XMLValidator(object):
    """XML validator for articles."""

    def __init__(self):
        xsd_filename = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "xsd/Clarivate_publishing.xsd")
        )
        self.validator = XMLValidatorWithSchema(xsd_filename)

    def validated_xml(self, textxml):
        validated = ValidatedXML(textxml)
        validated.validate(self.validator)
        return validated

    def validate_xml(self, textxml):
        validated_xml = self.validated_xml(textxml)
        if validated_xml.errors:
            removed, textxml = remove_contrib_id(textxml)
            if removed:
                validated_xml = self.validated_xml(textxml)
        return validated_xml
