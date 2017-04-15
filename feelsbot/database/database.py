import sqlite3


class Database:
    """
    General helper class to allow the server to open connections to the database.
    """

    _config = None
    _database = None

    @staticmethod
    def init_database(config):
        if Database._config is None:
            Database._config = config
            Database._database = config['database']

    @staticmethod
    def open():
        if Database._config is None:
            return None
        connect = sqlite3.connect(Database._database)
        connect.row_factory = sqlite3.Row
        return connect