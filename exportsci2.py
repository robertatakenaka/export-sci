# coding: utf-8
import argparse
import datetime
import logging
import os

from main.local_db_creator import harvest
from main.local_db_manager import LocalDBManager
from utils.file_utils import update_zipfile

import utils

logger = logging.getLogger(__name__)
config = utils.Configuration.from_env()
settings = dict(config.items())["main:exportsci"]

FTP_HOST = settings["ftp_host"]
FTP_USER = settings["ftp_user"]
FTP_PASSWD = settings["ftp_passwd"]
MONGODB_HOST = settings["mongodb_host"]
MONGODB_SLAVEOK = bool(settings["mongodb_slaveok"])
WOS_COLLECTIONS_ALLOWED = settings["wos_collections_allowed"].strip().split(",")
REPORT_PATH = settings["REPORT_PATH"]
XSD_VERSION = settings["XSD_VERSION"] or '1.12'
XSD_PATH = settings["XSD_PATH"] or 'Clarivate_publishing_1.12.xsd'
ZIP_PATH = settings["ZIP_PATH"]


def _config_logging(logging_level="INFO", logging_file=None):

    allowed_levels = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger.setLevel(allowed_levels.get(logging_level, "INFO"))

    if logging_file:
        hl = logging.FileHandler(logging_file, mode="a")
    else:
        hl = logging.StreamHandler()

    hl.setFormatter(formatter)
    hl.setLevel(allowed_levels.get(logging_level, "INFO"))

    logger.addHandler(hl)

    return logger


def get_issns(acronyms, issn, create_not_found=True):
    """
    Lê o arquivo keepinto.txt e os arquivos de cada coleção especificada nos acrônimos,
    retornando um dicionário com os ISSNs permitidos por coleção e opcionalmente gerando
    um arquivo com ISSNs não encontrados.

    Args:
        acronyms: Lista de acrônimos das coleções a serem processadas.
        create_not_found: Se True, cria o arquivo not_found.txt com ISSNs não encontrados
                         em nenhuma coleção. Padrão é True.

    Returns:
        Um dicionário com o acrônimo da coleção como chave e a lista de ISSNs permitidos como valor.
    """
    # Lê todos os ISSNs permitidos do arquivo keepinto.txt
    with open("controller/keepinto.txt", "r") as f:
        allowed_issns = {line.strip() for line in f if line.strip()}

    # Inicializa o dicionário de resultados e o conjunto de ISSNs encontrados
    collection_issns = {}
    found_issns = set()

    # Processa cada acrônimo da lista fornecida
    controller_dir = "controller"
    for acron in acronyms:
        filename = f"{acron}.txt"
        file_path = os.path.join(controller_dir, filename)

        # Verifica se o arquivo existe
        if os.path.exists(file_path):
            # Lê os ISSNs da coleção
            with open(file_path, "r") as f:
                collection_all_issns = {line.strip() for line in f if line.strip()}

            # Filtra apenas os ISSNs permitidos para esta coleção
            collection_allowed_issns = collection_all_issns.intersection(allowed_issns)

            # Adiciona ao dicionário de resultados
            if collection_allowed_issns:
                collection_issns[acron] = list(collection_allowed_issns)

                if issn and issn in collection_allowed_issns:
                    return {acron: [issn]}

                found_issns.update(collection_allowed_issns)

    # Encontra ISSNs que estão em keepinto mas não em nenhuma coleção
    not_found_issns = allowed_issns - found_issns

    # Escreve o arquivo not_found.txt se solicitado
    if create_not_found:
        with open(os.path.join(controller_dir, "not_found.txt"), "w") as f:
            f.write("\n".join(sorted(not_found_issns)))

    return collection_issns


def run(
    collection=None,
    issn=None,
    publication_year=None,
    add=None,
    sent_to_wos=None,
    has_errors=None,
    reproc=None,
):
    now = datetime.now().isoformat().replace(":", "").replace(".", "_")

    subdir = now[:10].split("-")[:2]
    subdir = os.path.join(REPORT_PATH, *subdir, now)

    summary_file = os.path.join(subdir, "summary.jsonl")
    with open(summary_file, "w") as fp:
        fp.write("")
    detail_file = os.path.join(subdir, "docs.jsonl")
    with open(detail_file, "w") as fp:
        fp.write("")

    xml_path = os.path.join(subdir, "xml")

    zip_filename = os.path.join(subdir, "scielo_{}.zip".format(now[:10]))

    error_path = os.path.join(subdir, "xml_error")

    if collection:
        issn_by_collection = get_issns(collection, issn, create_not_found=False)
    else:
        issn_by_collection = get_issns(
            WOS_COLLECTIONS_ALLOWED, issn, create_not_found=True
        )

    harvest(issn_by_collection)

    if publication_year:
        publication_years = [publication_year]
    else:
        publication_years = range(2002, datetime.now().year + 2)

    for collection, issns in issn_by_collection.items():
        for code_title in issns:

            xml_file = os.path.join(
                xml_path, "SciELO_{}_{}.xml".format(now[:10], code_title))
            if os.path.isfile(xml_file):
                os.unlink(xml_file)

            for publication_year in publication_years:
                # Instancia o gerenciador
                # xml_file = os.path.join(xml_path, f"{collection}-{code_title}-{publication_year}.xml")
                manager = LocalDBManager(
                    collection, code_title, publication_year,
                    summary_file,
                    detail_file,
                    xml_file,
                    XSD_VERSION,
                    XSD_PATH,
                    error_path,
               )

                # seleciona docs
                docs = manager.get_documents(add, sent_to_wos, reproc, has_errors)

                # target = 'scielo_{0}.zip'.format(now)
                result = manager.process_documents(docs)

    update_zipfile(
        zip_filename, 
        [os.path.join(xml_path, f) for f in os.listdir(xml_path)],
        mode="w",
        delete=True,
    )


def main():
    here = os.path.abspath(os.path.dirname(__file__))
    with open(os.path.join(here, "VERSION")) as f:
        VERSION = f.read()
        print("Export SciELOCI %s" % VERSION)

    parser = argparse.ArgumentParser(
        description="Control the process of sending metadata to WoS"
    )

    parser.add_argument(
        "-c",
        "--collection",
        default=None,
        help="Collection acronym",
    )

    parser.add_argument(
        "-i",
        "--issn",
        default=None,
        help="ISSN",
    )

    parser.add_argument(
        "-y",
        "--publication_year",
        default=None,
        help="publication year",
    )

    parser.add_argument(
        "-a",
        "--add",
        action="store_true",
        default=False,
        help="Executa para adicionar novos",
    )

    parser.add_argument(
        "-w",
        "--sent_to_wos",
        action="store_true",
        default=False,
        help="Reexecuta aqueles marcados como sent_to_wos=True",
    )

    parser.add_argument(
        "-r",
        "--reproc",
        action="store_true",
        default=False,
        help="Reexecuta aqueles que foram atualizados no AM",
    )

    parser.add_argument(
        "-e",
        "--has_errors",
        action="store_true",
        default=False,
        help="Reexecuta aqueles que obtiveram erros",
    )

    parser.add_argument(
        "--logging_file",
        "-o",
        default="/var/log/exportsci/export_sci.log",
        help="Full path to the log file",
    )

    parser.add_argument(
        "--logging_level",
        "-l",
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logggin level",
    )

    args = parser.parse_args()

    _config_logging(args.logging_level, args.logging_file)
    logging.debug("Export SciELOCI %s" % VERSION)
    run(
        collection=args.collection,
        issn=args.issn,
        publication_year=args.publication_year,
        add=args.add,
        sent_to_wos=args.sent_to_wos,
        has_errors=args.has_errors,
        reproc=args.reproc,
    )
