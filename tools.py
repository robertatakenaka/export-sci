# coding: utf-8
import re
from datetime import datetime
import os
import zipfile
from ftplib import FTP, error_perm
import logging

import requests
import pymongo
from pymongo import MongoClient
from lxml import etree
from lxml.etree import DocumentInvalid
from StringIO import StringIO

# SciELO article types stored in field v71 that are allowed to be sent to WoS
wos_article_types = ['ab', 'an', 'ax', 'co', 'cr', 'ct', 'ed', 'er', 'in',
                     'le', 'mt', 'nd', 'oa', 'pr', 'pv', 'rc', 'rn', 'ra',
                     'sc', 'tr', 'up']

wos_collections_allowed = ['scl', 'arg', 'cub', 'esp', 'col', 'ven', 'chl', 'sza', 'prt', 'cri', 'per', 'mex', 'ury', 'bol']


def write_log(msg):
    now = datetime.now().isoformat()[0:10]
    issn = msg.split(':')[1][1:10]
    error_report = open("reports/{0}_{1}_errors.txt".format(issn, now), "a")
    msg = u'%s\r\n' % msg
    try:
        error_report.write(msg.encode('utf-8'))
    except:
        logging.error('Error writing report line')

    error_report.close()


def ftp_connect(ftp_host='localhost',
                user='anonymous',
                passwd='anonymous'):

    ftp = FTP(ftp_host)
    ftp.login(user=user, passwd=passwd)

    return ftp


def send_to_ftp(file_name,
                ftp_host='localhost',
                user='anonymous',
                passwd='anonymous'):

    now = datetime.now().isoformat()[0:10]

    target = 'scielo_{0}.zip'.format(now)

    ftp = ftp_connect(ftp_host=ftp_host, user=user, passwd=passwd)
    f = open('{0}'.format(file_name), 'rd')
    ftp.storbinary('STOR inbound/{0}'.format(target), f)
    f.close()
    ftp.quit()
    logging.debug('file sent to ftp: %s' % target)


def send_take_off_files_to_ftp(ftp_host='localhost',
                               user='anonymous',
                               passwd='anonymous',
                               remove_origin=False):

    ftp = ftp_connect(ftp_host=ftp_host, user=user, passwd=passwd)

    for fl in os.listdir('controller'):
        if fl.split('.')[-1] == 'del':
            f = open('controller/{0}'.format(fl), 'rd')
            ftp.storbinary('STOR inbound/{0}'.format(fl), f)
            f.close()
            logging.debug('Takeoff file sent to ftp: %s' % fl)

            if remove_origin:
                os.remove('controller/{0}'.format(fl))
                logging.debug('Takeoff file removed from origin: %s' % fl)

    ftp.quit()


def remove_previous_unbound_files_from_ftp(ftp_host='localhost',
                           user='anonymous',
                           passwd='anonymous',
                           remove_origin=False):

    ftp = ftp_connect(ftp_host=ftp_host, user=user, passwd=passwd)
    ftp.cwd('inbound')
    report_files = ftp.nlst('*')

    for report_file in report_files:
        logging.debug('Previous unbound files removed from ftp: %s' % report_file)
        ftp.delete(report_file)


def get_sync_file_from_ftp(ftp_host='localhost',
                           user='anonymous',
                           passwd='anonymous',
                           remove_origin=False):

    ftp = ftp_connect(ftp_host=ftp_host, user=user, passwd=passwd)
    ftp.cwd('reports')
    report_files = ftp.nlst('SCIELO_ProcessedRecordIds*')
    with open('controller/validated_ids.txt', 'wb') as f:
        def callback(data):
            f.write(data)
        for report_file in report_files:
            ftp.retrbinary('RETR %s' % report_file, callback)

    ftp.quit()
    f.close()

    if remove_origin:
        for report_file in report_files:
            logging.debug('Syncronization files removed from ftp: %s' % report_file)
            ftp.delete(report_file)


def get_to_update_file_from_ftp(ftp_host='localhost',
                                user='anonymous',
                                passwd='anonymous',
                                remove_origin=False):

    ftp = ftp_connect(ftp_host=ftp_host, user=user, passwd=passwd)
    ftp.cwd('controller')
    with open('controller/toupdate.txt', 'wb') as f:
        def callback(data):
            f.write(data)
        try:
            ftp.retrbinary('RETR %s' % 'toupdate.txt', callback)
        except error_perm:
            return None

    if remove_origin:
        ftp.delete('toupdate.txt')

    ftp.quit()
    f.close()


def get_keep_into_file_from_ftp(ftp_host='localhost',
                                user='anonymous',
                                passwd='anonymous',
                                remove_origin=False):

    ftp = ftp_connect(ftp_host=ftp_host, user=user, passwd=passwd)
    ftp.cwd('controller')
    with open('controller/keepinto.txt', 'wb') as f:
        def callback(data):
            f.write(data)
        try:
            ftp.retrbinary('RETR %s' % 'keepinto.txt', callback)
        except error_perm:
            return None

    if remove_origin:
        ftp.delete('keepinto.txt')

    ftp.quit()
    f.close()


def get_take_off_files_from_ftp(ftp_host='localhost',
                                user='anonymous',
                                passwd='anonymous',
                                remove_origin=False):

    ftp = ftp_connect(ftp_host=ftp_host, user=user, passwd=passwd)
    ftp.cwd('controller')
    report_files = ftp.nlst('takeoff_*.del')
    with open('controller/takeoff.txt', 'wb') as f:
        def callback(data):
            f.write(data)
        for report_file in report_files:
            ftp.retrbinary('RETR %s' % report_file, callback)

    if remove_origin:
        for report_file in report_files:
            ftp.delete(report_file)

    ftp.quit()
    f.close()


def packing_zip(files):
    now = datetime.now().isoformat()[0:10]

    target = 'scielo_{0}.zip'.format(now)

    logging.info('zipping XML files to: %s' % target)

    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zipf:
        for xml_file in files:
            zipf.write('xml/{0}'.format(xml_file), arcname=xml_file)

    logging.debug('Files zipped into: %s' % target)

    return target


def load_journals_list(journals_file='journals.txt'):
    # ISSN REGEX
    prog = re.compile('^[0-9]{4}-[0-9]{3}[0-9X]$')

    issns = []
    with open(journals_file, 'r') as f:
        index = 0
        for line in f:
            index = index + 1
            if not '#' in line.strip() and len(line.strip()) > 0:
                issn = line.strip().upper()
                issn = prog.search(issn)
                if issn:
                    issns.append(issn.group())
                else:
                    logging.debug("Please check you journal.txt file, the input '{0}' at line '{1}' is not a valid issn".format(line.strip(), index))

    if len(issns) > 0:
        return issns
    else:
        return None


class XMLValidator(object):

    def __init__(self):
        str_schema = open(
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__), 'xsd/ThomsonReuters_publishing.xsd')), 'r')
        schema_doc = etree.parse(str_schema)
        self._schema = etree.XMLSchema(schema_doc)

    def validate_xml(self, collection, code):
        articlemeta_url = 'http://articlemeta.scielo.org/api/v1/article'

        params = {'collection': collection, 'code': code, 'format': 'xmlwos'}

        try:
            textxml = requests.get(articlemeta_url, params=params, timeout=30).text
        except:
            logging.error('error fetching url from articlemeta: %s' % articlemeta_url)
            return None

        xml = StringIO(textxml)

        ## Validating well formed
        try:
            parsedxml = etree.parse(xml)
        except:
            msg = u"%s:Not a well formed XML" % code
            write_log(msg)
            return None

        ## Validating agains schema
        try:
            result = self._schema.validate(parsedxml)
        except etree.XMLSyntaxError as e:
            msg = u"%s:XML Invalid" % code
            write_log(msg)
            return None

        if result:
            return parsedxml

        # Capturing validation errors
        try:
            self._schema.assertValid(parsedxml)
        except DocumentInvalid as e:
            for msg in [u'%s:%s:%s' % (collection, code, unicode(i)) for i in e.error_log]:
                write_log(msg)


class DataHandler(object):

    def __init__(
        self,
        mongodb_host='localhost',
        mongodb_port=27017,
        mongodb_database='articlemeta',
        mongodb_collection='articles'
    ):

        import pdb; pdb.set_trace()
        db = MongoClient(mongodb_host)[mongodb_database]

        self._articles_coll = self._set_articles_coll(db)
        self._collections_coll = self._set_collections_coll(db)

    def _set_articles_coll(self, db):

        coll = db['articles']
        coll.ensure_index('publication_year')
        coll.ensure_index('sent_wos')
        coll.ensure_index('applicable')

        return coll

    def _set_collections_coll(self, db):

        coll = db['collections']
        coll.ensure_index('code')

        return coll

    def load_pids_list_to_be_removed(self):

        now = datetime.now().isoformat()[0:10].replace('-', '')

        recorded_at = 'controller/SCIELO_DEL_{0}.del'.format(now)

        toremove = []

        with open(recorded_at, 'wb') as f:
            for line in open('controller/takeoff.txt', 'r'):
                sline = line.strip()
                toremove.append(sline)
                if len(sline) == 9:
                    for reg in self._articles_coll.find({'code_title': sline}, {'code': 1}):
                        f.write('SCIELO,{0},Y\r\n'.format(reg['code']))
                else:
                    f.write('SCIELO,{0},Y\r\n'.format(sline))

            f.close()

        return toremove


    def sync_sent_documents(self, remove_origin=False):

        with open('controller/validated_ids.txt', 'r') as f:
            for pid in f:
                self._articles_coll.update(
                    {'code': pid.strip()}, {'$set': {'sent_wos': 'True'}}
                )

        if remove_origin:
            os.remove('controller/validated_ids.txt')


    def load_collections_metadata(self):

        collections = self._collections_coll.find()

        dict_collections = {}
        for collection in collections:
            dict_collections.setdefault(collection['code'], collection)

        return dict_collections

    def set_elegible_document_types(self):
        documents = self._articles_coll.find({'applicable': 'False'}, {'collection': 1, 'code': 1, 'article.v71': 1})

        for document in documents:

            if not 'v71' in document['article']:
                continue

            if document['article']['v71'][0]['_'] in wos_article_types:
                self._articles_coll.update(
                    {'collection': document['collection'], 'code': document['code']}, {'$set': {'applicable': 'True'}}
                )

    def not_sent(self, code_title=None, publication_year=1800):
        """
        Implements an iterable article PID list not validated on SciELO.
        sent_wos = False
        """

        fltr = {'sent_wos': 'False',
                'applicable': 'True',
                'collection': {'$in': wos_collections_allowed},
                'publication_year': {'$gte': str(publication_year)}}

        if code_title:
            fltr.update({'code_title': code_title})

        documents = []
        total = 0
        for document in self._articles_coll.find(fltr, {'collection':1, 'code': 1}):
            total += 1
            documents.append([document['collection'], document['code']])

        i = 0
        for document in documents:
            i = i + 1
            yield [total, i, self._articles_coll.find_one({'collection': document[0], 'code': document[1]}, {'citations': 0})]

    def sent_to_wos(self, code_title=None):
        """
        Implements an iterable article PID list cotaining docs already sent to wos.
        sent_wos = True
        """

        fltr = {'sent_wos': 'True'}

        if code_title:
            fltr.update({'code_title': code_title})

        documents = []
        total = 0
        for document in self._articles_coll.find(fltr, {'code': 1}):
            total += 1
            documents.append([document['collection'], document['code']])

        i = 0
        for document in documents:
            i += 1
            yield [total, i, self_articles_coll.find_one({'collection': document[0], 'code': document[1]}, {'citations': 0})]
