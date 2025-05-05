# coding: utf-8
import os
import logging
import contextlib
from ftplib import FTP, error_perm, all_errors
from datetime import datetime
from tempfile import TemporaryDirectory

from file_utils import delete_file_or_folder
from collection_reports import CollectionReports
from ftp_client import FTPClient


class FTPService:
    def __init__(
        self,
        host: str,
        port: int = 21,
        username: str = "",
        password: str = "",
        timeout: int = 30,
        passive: bool = True,
    ):
        """
        Inicializa o cliente FTP.

        Args:
            host: Endereço do servidor FTP
            port: Porta do servidor FTP (padrão: 21)
            username: Nome de usuário para autenticação
            password: Senha para autenticação
            timeout: Tempo limite para conexão em segundos
            passive: Modo de conexão passiva (True) ou ativa (False)
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.passive = passive
        self.ftp = None

    def upload_file(self, local_file_path, remote_path):
        """Send file to FTP server."""
        # now = datetime.now().isoformat()[0:10]
        # target = 'scielo_{0}.zip'.format(now)

        with FTPClient(
            host=self.host,
            username=self.username,
            password=self.password,
        ) as ftp:
            # Fazer upload de um arquivo para uma subpasta
            target = os.path.join(remote_path, os.path.basename(local_file_path))
            ftp.upload_file(
                local_file_path=local_file_path,
                remote_path=target,
                create_missing_dirs=True,
            )

    def download_files(self, local_path, remote_path, delete_remote=False):
        """Send take-off files to FTP server."""
        with FTPClient(
            host=self.host,
            username=self.username,
            password=self.password,
        ) as ftp:
            for remote_file in ftp.list_directory(remote_path):
                ftp.download_file(
                    remote_path=f"{remote_path}/{remote_file}",
                    local_path=f"{local_path}/{remote_file}",
                    create_missing_dirs=True,
                    delete_remote=delete_remote,
                )

    def delete_directory_content(self, remote_path):
        """Send take-off files to FTP server."""
        with FTPClient(
            host=self.host,
            username=self.username,
            password=self.password,
        ) as ftp:
            for remote_file in ftp.list_directory(remote_path):
                ftp.delete_file(
                    remote_path=f"{remote_path}/{remote_file}",
                )

    def send_to_ftp(self, zip_file_path):
        self.upload_file(zip_file_path, "inbound")

    def send_take_off_files_to_ftp(self, remove_origin=False):
        for item in os.listdir("controller"):
            self.upload_file(
                os.path.join("controller", item), "inbound", delete_remote=remove_origin
            )

    def remove_previous_unbound_files_from_ftp(self, remove_origin):
        self.delete_directory_content("inbound")

    def get_sync_file_from_ftp(self, remove_origin=False):
        with TemporaryDirectory as tmpdir:
            self.download_files(
                local_path=tmpdir, remote_path="reports", delete_remote=remove_origin
            )

            with open("controller/validated_ids.txt", "w") as fpw:
                fpw.write("")
            for item in os.listdir(tmpdir):
                if item.startswith("SCIELO_ProcessedRecordIds"):
                    with open("controller/validated_ids.txt", "a") as fpw:
                        with open(os.join.path(tmpdir, item), "r") as fp:
                            fpw.write(fp.read())

    def get_to_update_file_from_ftp(self, remove_origin=False):
        """Get to-update file from FTP server."""
        return self.download_file("controller/toupdate.txt", "controller/toupdate.txt")

    def get_keep_into_file_from_ftp(self, remove_origin=False):
        """Get keep-into file from FTP server."""
        return self.download_file("controller/keepinto.txt", "controller/keepinto.txt")

    def get_take_off_files_from_ftp(self, remove_origin=False):
        """Get take-off files from FTP server."""
        with TemporaryDirectory as tmpdir:
            self.download_files(
                local_path=tmpdir, remote_path="controller", delete_remote=remove_origin
            )

            with open("controller/takeoff.txt", "w") as fpw:
                fpw.write("")
            for item in os.listdir(tmpdir):
                if item.startswith("takeoff_") and item.endswith(".del"):
                    with open("controller/takeoff.txt", "a") as fpw:
                        with open(os.join.path(tmpdir, item), "r") as fp:
                            fpw.write(fp.read())
