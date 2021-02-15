from django.core.files.storage import Storage
from fdfs_client.client import Fdfs_client, get_tracker_conf
from django.conf import settings


class FDFSStorage(Storage):
    """fast_DFS文件存储类"""
    def __init__(self, client_conf=None, base_url=None):
        if client_conf is None:
            # client_conf = get_tracker_conf(r"J:\django\dailyfresh\utils\fdfs\client.conf")
            client_conf = get_tracker_conf(settings.FDFS_CLIENT_CONF)
            self.client_conf = client_conf
        if base_url is None:
            base_url = settings.FDFS_URL

        self.client_conf = client_conf
        self.base_url = base_url

    def _open(self, name, mode='rb'):
        """打开文件时使用"""
        pass

    def _save(self, name, content):
        """保存文件时使用"""
        # name:你选择上传的文件的名字
        # content:包含你上传的文件内容的File对象
        client = Fdfs_client(self.client_conf)
        res = client.upload_by_buffer(content.read())
        if res.get('Status') != 'Upload successed.':
            # 上传失败
            raise Exception('上传文件到fast_DFS失败')

        # 获取上传文件返回的id
        file_id = res.get('Remote file_id').decode()

        return file_id

    def exists(self, name):
        # 返回name是否存在

        return False

    def url(self, name):
        return self.base_url + name

