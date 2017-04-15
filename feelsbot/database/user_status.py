import json

from .database import Database


QUERIES = {
    'select_row': 'SELECT * FROM user_status WHERE user_id = ?',
    'update_status': 'UPDATE user_status SET status = ?, data = ? WHERE user_id = ?',
    'insert_status': 'INSERT INTO user_status(user_id) SELECT ? WHERE (SELECT Changes() = 0)'
}


class UserStatusTable:
    """
    Class for manipulation of the 'user_status' table in the database.
    """

    def __enter__(self):
        self._connect = Database.open()
        self._cursor = self._connect.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._connect.close()

    def _select_row(self, user_id):
        row = self._cursor.execute(QUERIES['select_row'], [user_id]).fetchone()
        return row

    def _update_status(self, user_id, status, data=None):
        self._cursor.execute(QUERIES['update_status'], [status, data, user_id])
        self._cursor.execute(QUERIES['insert_status'], [user_id])

    def status(self, user_id):
        """
        ???
        :param user_id:
        :return:
        """
        row = self._select_row(user_id)
        if row is None:
            return 0, None
        try:
            data = json.loads(row['data'])
        except ValueError:
            data = None
        return int(row['status']), data

    def update(self, user_id, status, data=None):
        """
        ???
        :param user_id:
        :param status:
        :param data:
        :return:
        """
        dump = json.dumps(data)
        with self._connect:
            self._update_status(user_id, status, dump)
