# coding: utf-8
import os
import shutil
import zipfile
import logging
from datetime import datetime


def create_zip_from_string(
    zip_filename, content, filename, mode="w", compression=zipfile.ZIP_DEFLATED
):
    """
    Cria um arquivo zip contendo um único arquivo com o conteúdo fornecido.

    Args:
        content (str ou bytes): Conteúdo a ser incluído no arquivo
        filename (str): Nome do arquivo a ser criado dentro do zip
        zip_filename (str): Nome do arquivo zip a ser criado.
        compression (int, optional): Método de compressão. Padrão: ZIP_DEFLATED

    Returns:
        str: Caminho do arquivo zip criado
    """
    # Cria o arquivo zip em memória e adiciona o conteúdo
    with zipfile.ZipFile(zip_filename, "w", compression=compression) as zip_file:
        zip_file.writestr(filename, content)

    # Retorna o caminho do arquivo zip criado
    return zip_filename


def delete_file_or_folder(path):
    """Delete file or folder at given path."""
    if os.path.isdir(path):
        for item in os.listdir(path):
            delete_file_or_folder(path + "/" + item)
        try:
            shutil.rmtree(path)
        except:
            logging.info("Unable to delete: %s" % path)

    elif os.path.isfile(path):
        try:
            os.unlink(path)
        except:
            logging.info("Unable to delete: %s" % path)


def write_file(filename, content, mode="w"):
    """Write content to file."""
    try:
        with open(filename, mode) as f:
            f.write(content)
    except (IOError, ValueError):
        logging.error("Error writing file: %s" % filename, exc_info=True)
    except Exception as e:
        logging.exception("file_utils.write_file(): %s" % filename, e)


def update_zipfile(zip_filename, files, mode="w", delete=False):
    """Update a zip file with the specified files."""
    with zipfile.ZipFile(
        zip_filename, mode, compression=zipfile.ZIP_DEFLATED, allowZip64=True
    ) as zipf:
        for file in files:
            name = os.path.basename(file)
            zipf.write(file, arcname=name)
            if delete is True:
                delete_file_or_folder(file)
    logging.info("Files zipped into: %s" % zip_filename)
