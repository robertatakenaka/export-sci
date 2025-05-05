"""
Módulo para gerenciamento local de documentos WoS e manipulação de XML
"""

import os
import json
import logging
from datetime import datetime
from lxml import etree

from wos_documents import WosDocument
from xml_processing import get_xml_text, XMLValidator

logger = logging.getLogger(__name__)


class LocalDBManager:
    def __init__(
        self,
        collection,
        code_title,
        publication_year,
        summary_file,
        detail_file,
        xml_file,
        xsd_version,
        xsd_path,
        error_path,
    ):
        self.collection = collection
        self.code_title = code_title
        self.publication_year = publication_year
        self.validator = XMLValidator()
        self.error_path = error_path
        self.detail_file = detail_file
        self.xml_file = xml_file
        self.xsd_version = xsd_version
        self.xsd_path = xsd_path
        self.summary_file = summary_file

    def get_documents(self, add=None, sent_to_wos=None, reproc=None, has_errors=None):
        """Retorna documentos pendentes pela tupla (collection, code_title, publication_year)"""
        if add:
            yield from WosDocument.get_pending(
                collection=self.collection,
                code_title=self.code_title,
                publication_year=self.publication_year,
            )

        if reproc:
            yield from WosDocument.get_reproc(
                collection=self.collection,
                code_title=self.code_title,
                publication_year=self.publication_year,
            )

        if sent_to_wos:
            yield from WosDocument.get_sent_to_wos(
                collection=self.collection,
                code_title=self.code_title,
                publication_year=self.publication_year,
                sent_wos=sent_to_wos,
            )

        if has_errors:
            yield from WosDocument.get_with_errors(
                collection=self.collection,
                code_title=self.code_title,
                publication_year=self.publication_year,
            )

    def fetch_xml_from_articlemeta(self, code):
        """Busca XML do documento no ArticleMeta"""
        try:
            return get_xml_text(self.collection, code)
        except Exception as e:
            logging.exception(f"Erro ao buscar XML para {code}: {e}")
            return None

    def update_document_status(self, document, article_element=None, errors=None):
        """Atualiza o status do documento no banco de dados"""
        data = {
            "code": document.code,
        }

        if article_element:
            data["xml_date"] = datetime.utcnow()

        if errors:
            data["errors"] = errors
            data["has_error"] = True
        else:
            data["errors"] = []
            data["has_error"] = False

        return WosDocument.create_or_update(data)

    def save_individual_xml(self, code, xml_text):
        """Salva um elemento XML de artigo em um arquivo individual seguindo o padrão de diretórios"""
        try:
            # Cria o caminho do diretório com o padrão: pasta XML / collection / code_title / publication_year
            xml_dir = os.path.join(
                self.xml_folder, self.collection, self.code_title, self.publication_year
            )
            os.makedirs(xml_dir, exist_ok=True)

            # Nome do arquivo: code.xml
            xml_file = os.path.join(xml_dir, f"{code}.xml")
            with open(xml_file, "w") as fp:
                fp.write(xml_text)
            return True, xml_file
        except Exception as e:
            logging.exception(f"Erro ao salvar XML para o arquivo: {e}")
            return False, str(e)

    def append_to_xml_file(self, article_element):
        """Adiciona um elemento XML de artigo ao arquivo acumulador"""
        try:
            # Verifica se o arquivo já existe
            if os.path.exists(self.xml_file):
                # Carrega o arquivo XML existente
                parser = etree.XMLParser(remove_blank_text=True)
                global_xml = etree.parse(self.xml_file, parser).getroot()
            else:
                # Cria um novo documento XML com os namespaces corretos
                nsmap = {
                    'xml': 'http://www.w3.org/XML/1998/namespace',
                    'xlink': 'http://www.w3.org/1999/xlink'
                }
                global_xml = etree.Element('articles', nsmap=nsmap)
                global_xml.set('dtd-version', self.xsd_version)
                global_xml.set('{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation', 
                              self.xsd_path)
            # Adiciona o artigo ao XML global
            global_xml.append(article_element)
            
            # Salva o arquivo XML atualizado
            tree = etree.ElementTree(global_xml)
            tree.write(self.xml_file, encoding='utf-8', xml_declaration=True, pretty_print=True)
            
            return True
        except Exception as e:
            logging.exception(f"Erro ao adicionar XML ao arquivo: {e}")
            return False

    def save_error_file(self, code, xml_and_errors):
        """Salva arquivo de erro com XML e mensagens de erro"""
        self.error_path = self.error_path or "XML_ERRORS"
        try:
            # Cria a pasta de erro se não existir
            error_path = os.path.join(
                self.error_path, self.collection, self.code_title
            )
            os.makedirs(error_path, exist_ok=True)

            # Nome do arquivo de erro
            error_file = os.path.join(error_path, f"{code}.err.txt")

            # Salva o arquivo
            with open(error_file, "w", encoding="utf-8") as f:
                f.write(xml_and_errors)

            return True
        except Exception as e:
            logging.exception(f"Erro ao salvar arquivo de erro: {e}")
            return False

    def write_summary_file(self, result_data):
        """Cria um arquivo de log com informações sumarizadas do processamento"""
        try:
            with open(self.summary_file, "a", encoding="utf-8") as f:
                result_data.update(
                    {
                        "collection": self.collection,
                        "code_title": self.code_title,
                        "publication_year": self.publication_year,
                    }
                )
                fp.write(json.dumps(result_data) + "\n")
            return True
        except Exception as e:
            logging.exception(f"Erro ao criar arquivo de log sumarizado: {e}")
            return False

    def append_jsonl_metadata(self, doc, article_element, errors):
        """Adiciona dados ao arquivo JSONL"""
        try:
            with open(self.detail_file, "a", encoding="utf-8") as f:
                updates = {
                    "code": doc.code,
                    "collection": self.collection,
                    "code_title": self.code_title,
                    "publication_year": self.publication_year,
                    "xml_created": bool(article_element),
                    "has_errors": bool(errors),
                }
                f.write(json.dumps(updates) + "\n")
            return True
        except Exception as e:
            logging.warning(f"Erro ao adicionar dados ao JSONL: {e}")
            return False

    def process_documents(self, docs):
        """Processa documentos, busca XMLs e cria arquivos XML individuais"""
        success = 0
        failure = 0

        now = datetime.now().isoformat().replace(":", "").replace(".", "_")
        jsonl_file = os.path.join(
            self.report_path,
            self.collection,
            self.code_title,
            self.publication_year,
            now + ".jsonl",
        )
        # Preparar nomes dos arquivos de saída
        jsonl_file = f"{filename}.jsonl"

        # Processar cada documento
        idx = 0
        for idx, doc in enumerate(docs, 1):
            article_element, errors = self.process_document(doc)
            if errors:
                failure += 1
            else:
                success += 1

        # Preparar resultado do processamento
        result = {
            "total_docs": idx,
            "total_success": success,
            "total_failure": failure,
            "jsonl_file": jsonl_file if success > 0 else None,
        }

        # Criar log sumarizado
        self.write_summary_file(result)
        return result

    def process_document(self, doc):
        """Processa documentos, busca XMLs e cria arquivo acumulado"""
        # Busca o XML no ArticleMeta
        xml_text = self.fetch_xml_from_articlemeta(doc.code)

        if not xml_text:
            return None, ["Falha ao obter XML do ArticleMeta"]

        # Valida o XML e obtém o elemento article
        validated = self.validator.validate_xml(xml_text)
        article_element = validated.article
        errors = validated.errors

        # Atualiza o status do documento
        if article_element:
            if not errors:
                # self.save_individual_xml(doc.code, xml_text)
                self.append_to_xml_file(article_element)
            self.update_document_status(
                doc, article_element=article_element, errors=errors
            )

        # Se houver erros, salva o arquivo de erro
        if errors:
            self.save_error_file(doc.code, validated.get_report_content())

        self.append_jsonl_metadata(doc, article_element, errors)
        return article_element, errors


# Exemplo de uso
if __name__ == "__main__":
    # Parametros
    collection = "SCI"
    code_title = "1234-5678"
    publication_year = "2022"
    output_basename = f"{collection}_{code_title}_{publication_year}"
    xml_folder = "XML"
    error_folder = "errors"

    # Instancia o gerenciador
    manager = LocalDBManager(
        collection, code_title, publication_year, xml_folder, error_folder
    )

    # Obtém documentos pendentes ou pode usar qualquer outro método de obtenção
    docs = manager.get_documents(sent_to_wos=False, reproc=False, has_errors=False)

    # Processa os documentos
    result = manager.process_documents(docs, output_basename)

    print(
        f"Processamento concluído: {result['processed']}/{result['total_docs']} documentos processados"
    )
    print(f"Documentos com erro: {result['errors']}")

    if result["processed"] > 0:
        xml_path = os.path.join(
            result["output_folder"], collection, code_title, publication_year
        )
        print(f"Pasta de saída XML: {xml_path}")
        print(f"Arquivo JSONL com detalhes: {result['jsonl_file']}")
        print(f"Arquivo de log sumarizado: {result['summary_log']}")
    else:
        print(
            "Nenhum arquivo foi gerado devido à ausência de documentos processados com sucesso."
        )
