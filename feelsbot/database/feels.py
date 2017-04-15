import random

from .database import Database


QUERIES = {
    'select_row': 'SELECT * FROM feels WHERE feel_id = ?',
    'select_not_approved': 'SELECT * FROM feels WHERE approved = 0',
    'insert_feel': 'INSERT INTO feels(submitted, name, comment) VALUES (?, ?, ?)',
    'update_approved': 'UPDATE feels SET approved = 1 WHERE feel_id = ?',
    'update_not_approved': 'UPDATE feels SET approved = 0 WHERE feel_id = ?',
    'update_blocked': 'UPDATE feels SET approved = -1 WHERE feel_id = ?',
    'update_selector': 'UPDATE feels SET selector = ? WHERE feel_id = ?',
    'update_feel_count': 'UPDATE feels SET selector = (SELECT selector FROM feels WHERE feel_id = ?) + 1, '
                         'sent_count = (SELECT sent_count FROM feels WHERE feel_id = ?) + 1 WHERE feel_id = ?',
    'min_selector': 'SELECT min(selector) FROM feels WHERE approved = 1',
    'random_feel_ids': 'SELECT feel_id FROM feels WHERE approved = 1 AND selector <= ?',
    'count_all': 'SELECT count(feel_id) FROM feels',
    'count_approved': 'SELECT count(feel_id) FROM feels WHERE approved = 1',
    'count_not_approved': 'SELECT count(feel_id) FROM feels WHERE approved = 0',
    'count_blocked': 'SELECT count(feel_id) FROM feels WHERE approved = -1',
}


class FeelsTable:
    """
    Class for manipulation of the 'feels' table in the database.
    """

    def __enter__(self):
        self._connect = Database.open()
        self._cursor = self._connect.cursor()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._connect.close()

    def _select_row(self, feel_id):
        row = self._cursor.execute(QUERIES['select_row'], [feel_id]).fetchone()
        return row

    def _min_selector(self):
        return self._cursor.execute(QUERIES['min_selector']).fetchone()[0]

    def _update_approved(self, feel_id):
        self._cursor.execute(QUERIES['update_approved'], [feel_id])

    def _update_not_approved(self, feel_id):
        self._cursor.execute(QUERIES['update_not_approved'], [feel_id])

    def _update_blocked(self, feel_id):
        self._cursor.execute(QUERIES['update_blocked'], [feel_id])

    def _update_selector(self, feel_id, selector=None):
        if selector is None:
            self._cursor.execute(QUERIES['update_feel_count'], (feel_id, feel_id, feel_id))
        else:
            self._cursor.execute(QUERIES['update_selector'], (selector, feel_id))

    def _is_not_approved(self, feel_id):
        row = self._select_row(feel_id)
        return row['approved'] == 0

    def _is_blocked(self, feel_id):
        row = self._select_row(feel_id)
        return row['approved'] == -1

    def insert_feel(self, submitted, name, comment):
        """
        Add a new feel to the database.
        :param submitted: The date / time it was submitted.
        :param name: The name (as per the form) of the person adding the feel.
        :param comment: The feel comment to add.
        :return:
        """
        with self._connect:
            self._cursor.execute(QUERIES['insert_feel'], (submitted, name, comment))

    def insert_feels(self, feels):
        """
        Add multiple feels to the database at the same time.
        :param feels: A list containing tuples with multiple sets of values for submitted, name and comment.
        :return:
        """
        with self._connect:
            self._cursor.executemany(QUERIES['insert_feel'], feels)

    def count_all(self):
        """
        Count the total number of feels (including those awaiting approval or blocked).
        :return: The number of rows in the table.
        """
        return self._cursor.execute(QUERIES['count_all']).fetchone()[0]

    def count_need_approval(self):
        """
        Count the number of feels awaiting admin approval.
        :return: The number of rows requiring approval.
        """
        return self._cursor.execute(QUERIES['count_not_approved']).fetchone()[0]

    def count_blocked(self):
        """
        Count the number of feels that are currently blocked.
        :return: The number of rows that have been blocked.
        """
        return self._cursor.execute(QUERIES['count_blocked']).fetchone()[0]

    def select_random_feel(self):
        """
        Select a random feel from those eligible.

        Specifically, this will limit the selection of feels to those that are not blocked and have a selector value
        within 1 of the lowest selector value in the table. This ensures that all messages will (eventually) be sent to
        the recipient and that no messages will be sent overly often.

        Long term, we could rely on the distribution from the pseudo-random selection, but in practice this leads to
        "clumping" where the same message is selected multiple times in a relatively small number of selections. Hence
        this approach was developed to smooth out the distribution and appears to be working.

        :return: An object containing the fields of the selected row in the table.
        """
        min_selector = self._min_selector()

        feels = self._cursor.execute(QUERIES['random_feel_ids'], [min_selector + 1]).fetchall()
        rand = random.randrange(len(feels))
        feel_id = feels[rand]['feel_id']

        with self._connect:
            self._update_selector(feel_id)
            row = self._cursor.execute(QUERIES['select_row'], [feel_id]).fetchone()
            return row

    def select_unapproved(self):
        """
        Select a row that contains a feel that is not approved.
        :return: A object containing the fields of the selected row in the table.
        """
        feel = self._cursor.execute(QUERIES['select_not_approved']).fetchone()
        return feel

    def approve(self, feel_id):
        """
        Set a feel to approved status (if it is awaiting approval, see unblock_feel() for approving a blocked message).
        Will also ensure that the selector is set to a reasonable value.
        :param feel_id: The id of the row to approve.
        :return:
        """
        if not self._is_not_approved(feel_id):
            # TODO maybe exception here?
            return

        with self._connect:
            min_selector = self._min_selector()
            self._update_approved(feel_id)
            if min_selector > 0:
                self._update_selector(feel_id, min_selector)

    def block(self, feel_id):
        """
        Set blocked status on a feel.
        :param feel_id: The id of the row to block.
        :return:
        """
        with self._connect:
            self._update_blocked(feel_id)

    def unblock(self, feel_id):
        """
        Unblock (and indirectly approve) a feel. This will also sent the selector to a sane value based upon the current
        minimum, if necessary (avoid spamming the message multiple times if the current minimum selector is higher than
        the existing selector value on the blocked message).
        :param feel_id: The id of the row to unblock.
        :return:
        """
        if not self._is_blocked(feel_id):
            # TODO maybe exception here instead?
            return

        with self._connect:
            min_selector = self._min_selector()
            row = self._select_row(feel_id)
            self._update_approved(feel_id)
            if min_selector > row['selector']:
                self._update_selector(feel_id, min_selector)
