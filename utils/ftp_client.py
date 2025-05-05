import os
import ftplib


class FTPClient:
    """
    Classe genérica para operações FTP, incluindo manipulação de arquivos em subpastas.
    """

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

    def connect(self) -> bool:
        """
        Estabelece conexão com o servidor FTP.

        Returns:
            bool: True se a conexão for bem-sucedida, False caso contrário.
        """
        try:
            self.ftp = ftplib.FTP()
            self.ftp.connect(self.host, self.port, self.timeout)
            self.ftp.login(self.username, self.password)
            self.ftp.set_pasv(self.passive)
            return True
        except Exception as e:
            print(f"Erro ao conectar: {str(e)}")
            return False

    def disconnect(self) -> None:
        """
        Encerra a conexão com o servidor FTP.
        """
        if self.ftp and self.ftp.sock:
            try:
                self.ftp.quit()
            except:
                self.ftp.close()
            finally:
                self.ftp = None

    def list_directory(self, remote_path: str = "."):
        """
        Lista arquivos e diretórios no caminho remoto especificado.

        Args:
            remote_path: Caminho remoto para listar (padrão: diretório atual)

        Returns:
            Lista de nomes de arquivos e diretórios
        """
        if not self.ftp:
            if not self.connect():
                return []

        try:
            return self.ftp.nlst(remote_path)
        except Exception as e:
            print(f"Erro ao listar diretório {remote_path}: {str(e)}")
            return []

    def create_directory(self, remote_path: str) -> bool:
        """
        Cria um diretório no servidor FTP.

        Args:
            remote_path: Caminho do diretório a ser criado

        Returns:
            bool: True se bem-sucedido, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        try:
            self.ftp.mkd(remote_path)
            return True
        except Exception as e:
            print(f"Erro ao criar diretório {remote_path}: {str(e)}")
            return False

    def create_directories(self, remote_path: str) -> bool:
        """
        Cria diretórios recursivamente se não existirem.

        Args:
            remote_path: Caminho completo a ser criado

        Returns:
            bool: True se bem-sucedido, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        # Remove barras iniciais e finais
        path = remote_path.strip("/")

        # Se não houver diretórios para criar
        if not path:
            return True

        # Dividir o caminho em partes
        dirs = path.split("/")

        # Começar do diretório raiz
        current_dir = ""

        for directory in dirs:
            if not directory:
                continue

            # Adicionar diretório ao caminho atual
            if current_dir:
                current_dir += f"/{directory}"
            else:
                current_dir = directory

            # Verificar se o diretório já existe
            try:
                self.ftp.cwd(current_dir)
                # Voltar ao diretório raiz
                self.ftp.cwd("/")
            except:
                # Se não existir, criar
                try:
                    self.ftp.mkd(current_dir)
                except Exception as e:
                    print(f"Erro ao criar diretório {current_dir}: {str(e)}")
                    return False

        return True

    def change_directory(self, remote_path: str) -> bool:
        """
        Muda o diretório de trabalho atual no servidor FTP.

        Args:
            remote_path: Caminho para o novo diretório de trabalho

        Returns:
            bool: True se bem-sucedido, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        try:
            self.ftp.cwd(remote_path)
            return True
        except Exception as e:
            print(f"Erro ao mudar para o diretório {remote_path}: {str(e)}")
            return False

    def get_current_directory(self) -> str:
        """
        Obtém o diretório de trabalho atual no servidor FTP.

        Returns:
            str: Caminho do diretório atual
        """
        if not self.ftp:
            if not self.connect():
                return ""

        try:
            return self.ftp.pwd()
        except Exception as e:
            print(f"Erro ao obter diretório atual: {str(e)}")
            return ""

    def upload_file(
        self, local_path: str, remote_path: str, create_missing_dirs: bool = True
    ) -> bool:
        """
        Faz upload de um arquivo para o servidor FTP, suportando subpastas.

        Args:
            local_path: Caminho local do arquivo para upload
            remote_path: Caminho remoto onde o arquivo será armazenado
            create_missing_dirs: Criar diretórios remotos se não existirem

        Returns:
            bool: True se bem-sucedido, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        if not os.path.isfile(local_path):
            print(f"Arquivo local não encontrado: {local_path}")
            return False

        try:
            # Obter o diretório pai do caminho remoto
            remote_dir = os.path.dirname(remote_path)

            # Se o diretório remoto não for vazio e for necessário criar diretórios ausentes
            if remote_dir and create_missing_dirs:
                self.create_directories(remote_dir)

            # Abrir o arquivo local para leitura em modo binário
            with open(local_path, "rb") as file:
                # Obter apenas o nome do arquivo do caminho remoto
                remote_filename = os.path.basename(remote_path)
                if not remote_filename:
                    remote_filename = os.path.basename(local_path)

                # Se um diretório remoto foi especificado, alterar para ele
                if remote_dir:
                    original_dir = self.ftp.pwd()
                    try:
                        self.ftp.cwd(remote_dir)
                        # Fazer upload do arquivo
                        self.ftp.storbinary(f"STOR {remote_filename}", file)
                        # Voltar ao diretório original
                        self.ftp.cwd(original_dir)
                    except Exception as e:
                        print(f"Erro ao navegar para o diretório remoto: {str(e)}")
                        return False
                else:
                    # Fazer upload diretamente no diretório atual
                    self.ftp.storbinary(f"STOR {remote_filename}", file)

            return True
        except Exception as e:
            print(f"Erro ao fazer upload do arquivo {local_path}: {str(e)}")
            return False

    def download_file(
        self,
        remote_path: str,
        local_path: str,
        create_missing_dirs: bool = True,
        delete_remote: bool = False,
    ) -> bool:
        """
        Faz download de um arquivo do servidor FTP, suportando subpastas.

        Args:
            remote_path: Caminho remoto do arquivo para download
            local_path: Caminho local onde o arquivo será salvo
            create_missing_dirs: Criar diretórios locais se não existirem

        Returns:
            bool: True se bem-sucedido, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        try:
            # Obter o diretório pai do caminho local
            local_dir = os.path.dirname(local_path)

            # Se o diretório local não for vazio e for necessário criar diretórios ausentes
            if local_dir and create_missing_dirs:
                os.makedirs(local_dir, exist_ok=True)

            # Obter o diretório pai e o nome do arquivo do caminho remoto
            remote_dir = os.path.dirname(remote_path)
            remote_filename = os.path.basename(remote_path)

            if remote_dir:
                # Salvar diretório atual
                original_dir = self.ftp.pwd()
                # Mudar para o diretório remoto
                self.ftp.cwd(remote_dir)

                # Abrir o arquivo local para escrita em modo binário
                with open(local_path, "wb") as file:
                    # Fazer download do arquivo
                    self.ftp.retrbinary(f"RETR {remote_filename}", file.write)
                if delete_remote and os.path.isfile(local_path):
                    self.ftp(remote_filename)

                # Voltar ao diretório original
                self.ftp.cwd(original_dir)
            else:
                # Abrir o arquivo local para escrita em modo binário
                with open(local_path, "wb") as file:
                    # Fazer download do arquivo diretamente
                    self.ftp.retrbinary(f"RETR {remote_filename}", file.write)
                if delete_remote and os.path.isfile(local_path):
                    self.ftp(remote_filename)
            return True
        except Exception as e:
            print(f"Erro ao fazer download do arquivo {remote_path}: {str(e)}")
            # Remover arquivo local parcial em caso de erro
            if os.path.exists(local_path):
                try:
                    os.remove(local_path)
                except:
                    pass
            return False

    def delete_file(self, remote_path: str) -> bool:
        """
        Exclui um arquivo no servidor FTP.

        Args:
            remote_path: Caminho do arquivo a ser excluído

        Returns:
            bool: True se bem-sucedido, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        try:
            self.ftp.delete(remote_path)
            return True
        except Exception as e:
            print(f"Erro ao excluir arquivo {remote_path}: {str(e)}")
            return False

    def delete_directory(self, remote_path: str, recursive: bool = False) -> bool:
        """
        Exclui um diretório no servidor FTP.

        Args:
            remote_path: Caminho do diretório a ser excluído
            recursive: Se True, exclui recursivamente todos os arquivos e subdiretórios

        Returns:
            bool: True se bem-sucedido, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        if recursive:
            try:
                # Listar todos os itens no diretório
                items = self.list_directory(remote_path)

                # Salvar diretório atual
                original_dir = self.ftp.pwd()

                # Mudar para o diretório a ser excluído
                self.ftp.cwd(remote_path)

                # Excluir cada item dentro do diretório
                for item in items:
                    # Ignorar entradas especiais
                    if item in [".", ".."]:
                        continue

                    try:
                        # Tentar excluir como arquivo
                        self.ftp.delete(item)
                    except:
                        # Se falhar, tentar excluir como diretório recursivamente
                        self.delete_directory(f"{remote_path}/{item}", True)

                # Voltar ao diretório original
                self.ftp.cwd(original_dir)

                # Excluir o diretório vazio
                self.ftp.rmd(remote_path)

                return True
            except Exception as e:
                print(
                    f"Erro ao excluir diretório recursivamente {remote_path}: {str(e)}"
                )
                return False
        else:
            try:
                self.ftp.rmd(remote_path)
                return True
            except Exception as e:
                print(f"Erro ao excluir diretório {remote_path}: {str(e)}")
                return False

    def rename(self, from_path: str, to_path: str) -> bool:
        """
        Renomeia ou move um arquivo ou diretório no servidor FTP.

        Args:
            from_path: Caminho original
            to_path: Novo caminho

        Returns:
            bool: True se bem-sucedido, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        try:
            self.ftp.rename(from_path, to_path)
            return True
        except Exception as e:
            print(f"Erro ao renomear de {from_path} para {to_path}: {str(e)}")
            return False

    def file_exists(self, remote_path: str) -> bool:
        """
        Verifica se um arquivo existe no servidor FTP.

        Args:
            remote_path: Caminho do arquivo a verificar

        Returns:
            bool: True se o arquivo existir, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        try:
            # Obter o diretório pai e o nome do arquivo
            remote_dir = os.path.dirname(remote_path)
            remote_filename = os.path.basename(remote_path)

            # Se não houver diretório, usar o diretório atual
            if not remote_dir:
                remote_dir = "."

            # Listar os arquivos no diretório
            files = self.list_directory(remote_dir)

            # Verificar se o arquivo está na lista
            return remote_filename in files
        except Exception as e:
            print(f"Erro ao verificar existência do arquivo {remote_path}: {str(e)}")
            return False

    def directory_exists(self, remote_path: str) -> bool:
        """
        Verifica se um diretório existe no servidor FTP.

        Args:
            remote_path: Caminho do diretório a verificar

        Returns:
            bool: True se o diretório existir, False caso contrário
        """
        if not self.ftp:
            if not self.connect():
                return False

        try:
            # Salvar diretório atual
            current_dir = self.ftp.pwd()

            # Tentar mudar para o diretório
            self.ftp.cwd(remote_path)

            # Se chegou aqui, o diretório existe, então voltar ao diretório original
            self.ftp.cwd(current_dir)

            return True
        except:
            return False

    def __enter__(self):
        """
        Suporte para o uso com o gerenciador de contexto (with).
        """
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Encerrar a conexão ao sair do gerenciador de contexto.
        """
        self.disconnect()


# Exemplo de uso:
if __name__ == "__main__":
    # Criar uma instância do cliente FTP
    ftp = FTPClient(host="ftp.example.com", username="user", password="pass")

    # Usando com gerenciador de contexto (recomendado)
    with FTPClient(host="ftp.example.com", username="user", password="pass") as ftp:
        # Listar arquivos no diretório raiz
        files = ftp.list_directory()
        print(f"Arquivos no diretório raiz: {files}")

        # Fazer upload de um arquivo para uma subpasta
        ftp.upload_file(
            local_path="arquivo_local.txt",
            remote_path="pasta/subpasta/arquivo_remoto.txt",
            create_missing_dirs=True,
        )

        # Fazer download de um arquivo de uma subpasta
        ftp.download_file(
            remote_path="pasta/subpasta/arquivo_remoto.txt",
            local_path="download/arquivo_baixado.txt",
            create_missing_dirs=True,
        )
