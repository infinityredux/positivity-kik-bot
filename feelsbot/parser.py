from kik.messages import TextResponse

from .database import FeelsTable, UserStatusTable


SOURCE_ADMIN = {
    'unknown': 'Unknown trigger source:',
    'twitter': 'Triggered by lack of twitter:',
    'push': 'Triggered by Zapier push:',
    'admin': 'Triggered by admin request:',
    'recipient': 'Triggered by recipient request:',
    'manual': 'Manual message sent:',
    'schedule': 'Triggered as scheduled:'
}

SOURCE_RECIPIENT = {
    'unknown': "",
    'twitter': "You haven't sent a public tweet today, so just in case you're feeling a bit down, have this message:",
    'push': "Someone thought you might be feeling a bit down, so have this message:",
    'admin': "Someone thought you might be feeling a bit down, so have this message:",
    'recipient': "As requested, another message in case you need more feels:",
    'manual': "",
    'schedule': "",
}


class MessageParser:
    def __init__(self, config, queue):
        self.config = config
        self.queue = queue
        self.message = None

    def process_text_message(self, message):
        """
        Process a received message, generating an appropriate response.
        :param message: The message object to process, should be an instance of TextMessage.
        :return: Status code indicating the result of parsing the message.
        """
        self.message = message

        func = None
        admin = self._test_admin(message.from_user)
        recipient = self._test_recipient(message.from_user)

        if not (admin or recipient):
            func = user_invalid
        else:
            state, data = self.user_state()
            if state in STATUS_CUSTOM_MESSAGES.keys():
                func = STATUS_CUSTOM_MESSAGES.get(state)
            else:
                if message.body in MESSAGES_ADMIN.keys():
                    if not admin:
                        func = recipient_unknown_command
                    else:
                        func = MESSAGES_ADMIN.get(message.body)

                if message.body in MESSAGES_RECIPIENT.keys():
                    if not recipient:
                        func = admin_unknown_command
                    else:
                        func = MESSAGES_RECIPIENT.get(message.body)

        if func is None:
            if admin:
                func = admin_unknown_command
            else:
                func = recipient_unknown_command

        body, code = func(self)
        if code == 0:
            code = 200
        else:
            keyboard = self._current_keyboard()
            self._add_message(body, keyboard)

        self.message = None
        return code

    def _add_message(self, body, keyboards):
        """
        Helper shortcut for adding a message to the message queue.
        :param body: The text of the message to add.
        :return: Nothing.
        """
        self.queue.add_message(to=self.message.from_user, chat_id=self.message.chat_id, body=body, keyboards=keyboards)

    def recipient_message(self, body):
        to = self.config['recipient']
        keyboard = self.current_user_keyboard(to)
        self.queue.add_message(to=to, body=body, keyboards=keyboard)

    def _test_admin(self, user):
        return self.config['admin'] == user

    def _test_recipient(self, user):
        return self.config['recipient'] == user

    def user_state(self, user=None):
        """
        Obtain the current state for the user that sent the message being parsed.
        :return:
        """
        with UserStatusTable() as table:
            if user is None:
                return table.status(self.message.from_user)
            else:
                return table.status(user)

    def change_state(self, state, data=None):
        """
        Assign the state for the sender of the current message being parsed.
        :param state: The new state for that user.
        :param data: Any data to be saved with state code.
        :return: Nothing.
        """
        with UserStatusTable() as table:
            table.update(self.message.from_user, state, data)

    def default_state(self):
        """
        Shortcut for assigning the default state to the user for the current message.
        :return: Nothing.
        """
        self.change_state(STATE_DEFAULT)

    def _current_keyboard(self):
        """
        Shortcut helper method
        :return:
        """
        return self.current_user_keyboard(self.message.from_user)

    def current_user_keyboard(self, user):
        keyboard = keyboard_basic()
        state, data = self.user_state(user)
        admin = self._test_admin(user)
        recipient = self._test_recipient(user)

        if recipient:
            if state in KEYBOARDS_RECIPIENT.keys():
                func = KEYBOARDS_RECIPIENT.get(state)
                keyboard += func()
            else:
                keyboard += keyboard_recipient_default()

        if admin:
            if state in KEYBOARDS_ADMIN.keys():
                func = KEYBOARDS_ADMIN.get(state)
                keyboard += func()
            else:
                keyboard += keyboard_admin_default()

        return keyboard

    def queue_feel(self, source):
        with FeelsTable() as table:
            feel = table.select_random_feel()

        msg = u"\n\n{}\n\u00A0  \u2015{} ({})".format(feel['comment'], feel['name'], feel['submitted'])
        body_notify = SOURCE_ADMIN[source] + msg
        body_message = SOURCE_RECIPIENT[source] + msg

        self.queue.add_message(to=self.config['admin'],
                               body=body_notify,
                               keyboards=self.current_user_keyboard(self.config['admin']))

        self.queue.add_message(to=self.config['recipient'],
                               body=body_message,
                               keyboards=self.current_user_keyboard(self.config['recipient']))


# ======================================================================================================================


def zapier_error_handler(parser, response, source):
    """
    Error handler used by the functions called by the parser when interacting with Zapier. Specifically, if there is an
    error code returned from a push request to the server.
    :param parser: Reference to the parser object currently processing a message.
    :param response: The server response as a
    :param source:
    :return:
    """
    print("Error with posting to Zapier from {}.".format(source))
    print("Full response:\n{}".format(response))
    print("Requesting admin notification.")
    parser.queue.add_message(to=parser.config['admin'],
                             body="Error with request to Zapier. See Apache logs for details.")
    parser.queue.send_all()


# ======================================================================================================================


def user_invalid(parser):
    # Avoid IDE throwing up warning about not using parser parameter.
    # Will also not generate database entry as no update to the sate was triggered.
    parser.user_state()
    return REPLIES['invalid_user'], 200


def admin_error(parser):
    parser.default_state()
    return REPLIES['admin_error'], 200


def admin_reset(parser):
    parser.change_state(STATE_DEFAULT)
    return REPLIES['admin_reset'], 200


def admin_unknown_command(parser):
    parser.default_state()
    return REPLIES['admin_unknown_command'], 200


def recipient_reset(parser):
    parser.change_state(STATE_DEFAULT)
    return REPLIES['recipient_reset'], 200


def recipient_unknown_command(parser):
    parser.default_state()
    return REPLIES['recipient_unknown_command'], 200


# ----------------------------------------------------------------------------------------------------------------------


def admin_send_feel(parser):
    parser.queue_feel('admin')
    return None, 0


def admin_send_manual(parser):
    parser.change_state(STATE_ADMIN_MANUAL_MESSAGE)
    return REPLIES['admin_send_manual'], 200


def admin_manual_message(parser):
    msg = parser.message.body
    parser.change_state(STATE_ADMIN_MANUAL_CONFIRM, msg)
    return REPLIES['admin_confirm_manual'], 200


def admin_manual_confirm(parser):
    state, msg = parser.user_state()
    if state != STATE_ADMIN_MANUAL_CONFIRM:
        return admin_error(parser)

    to = parser.config['recipient']
    parser.queue.add_message(to=to, body=msg, keyboards=parser.current_user_keyboard(to))
    parser.default_state()
    return REPLIES['admin_manual_sent'], 200


def admin_status(parser):
    with FeelsTable() as table:
        msg = "Total feels: {}\nAwaiting approval: {}\nBlocked: {}"
        msg = msg.format(table.count_all(), table.count_need_approval(), table.count_blocked())
    parser.change_state(STATE_ADMIN_STATUS_REQUEST)
    return msg, 200


def admin_approve_new(parser):
    with FeelsTable() as table:
        if table.count_need_approval() < 1:
            return admin_error(parser)
        feel = table.select_unapproved()
        msg = "From: {}\nDate: {}\nComment:\n{}".format(feel['name'], feel['submitted'], feel['comment'])
    parser.change_state(STATE_ADMIN_APPROVE_MESSAGE, feel['feel_id'])
    return msg, 200


def admin_approve(parser):
    state, feel_id = parser.user_state()
    if state != STATE_ADMIN_APPROVE_MESSAGE:
        return admin_error(parser)

    with FeelsTable() as table:
        table.approve(feel_id)
    parser.change_state(STATE_ADMIN_STATUS_REQUEST)
    return REPLIES['admin_approve'], 200


def admin_block(parser):
    state, feel_id = parser.user_state()
    if state != STATE_ADMIN_APPROVE_MESSAGE:
        return admin_error(parser)

    with FeelsTable() as table:
        table.block(feel_id)
    parser.change_state(STATE_ADMIN_STATUS_REQUEST)
    return REPLIES['admin_block'], 200


# ----------------------------------------------------------------------------------------------------------------------


def recipient_request_feel(parser):
    parser.queue_feel('recipient')
    return None, 0


# ======================================================================================================================


def keyboard_basic():
    """
    Create a basic keyboard. This will only have any responses that are applicable in all situations.
    :return: An array with the responses that should be sent on the present message.
    """
    return []


def keyboard_empty():
    """
    Create an explicitly empty keyboard.
    :return: An empty list.
    """
    return []


def keyboard_admin_default():
    """
    Create default keyboard responses that are sent to an admin user.
    :return: An array with the responses that should be sent on the present message.
    """
    return [
        TextResponse(BUTTONS['admin_send_feel']),
        TextResponse(BUTTONS['admin_status']),
        TextResponse(BUTTONS['admin_send_manual']),
    ]


def keyboard_admin_status():
    """
    Keyboard for the system status report, allowing options related to the status.
    :return:
    """
    keyboard = []
    with FeelsTable() as table:
        if table.count_need_approval() > 0:
            keyboard += [
                TextResponse(BUTTONS['admin_approve_new']),
            ]
    keyboard += [
        TextResponse(BUTTONS['admin_reset']),
    ]
    return keyboard


def keyboard_admin_approval():
    """
    Keyboard for approving or blocking a new feels message.
    :return:
    """
    return [
        TextResponse(BUTTONS['admin_approve']),
        TextResponse(BUTTONS['admin_block']),
        TextResponse(BUTTONS['admin_reset']),
    ]


def keyboard_admin_confirm_manual():
    """
    Keyboard for confirming a manual message.
    :return:
    """
    return [
        TextResponse(BUTTONS['admin_confirm_manual']),
        TextResponse(BUTTONS['admin_reset']),
    ]


def keyboard_recipient_default():
    """
    Create keyboard responses that are sent to a message recipient.
    :return: An array with the responses that should be sent on the present message.
    """
    return [TextResponse(BUTTONS['recipient_request_feel'])]


# ======================================================================================================================

# Keeping constants in a consistent place
# Also makes for easier reading / reference

STATE_DEFAULT = 0

STATE_ADMIN_STATUS_REQUEST = 100
STATE_ADMIN_APPROVE_MESSAGE = 101
STATE_ADMIN_MANUAL_MESSAGE = 110
STATE_ADMIN_MANUAL_CONFIRM = 111

STATE_RECIPIENT_SOMETHING = 500

BUTTONS = {
    'admin_approve_new': 'Approve new feels',
    'admin_approve': 'Approve feel',
    'admin_block': 'Block feel',
    'admin_confirm_manual': 'Confirm manual message',
    'admin_reset': 'Return to Admin Menu',
    'admin_send_feel': 'Send feels',
    'admin_send_manual': 'Send manual message',
    'admin_status': 'System status',
    'recipient_request_feel': 'Get more feels',
    'recipient_reset': 'Return to Main Menu',
    'recipient_reset_alt': 'Cancel',
}
REPLIES = {
    'admin_approve': 'Message approved.',
    'admin_block': 'Message blocked.',
    'admin_confirm_manual': 'Are you certain you wish to send this message?',
    'admin_error': 'I cannot perform that function at the present time. (Invalid state.)',
    'admin_manual_sent': 'Manual message sent.',
    'admin_reset': 'What function do you require?',
    'admin_send_manual': 'Enter your custom message here:',
    'admin_unknown_command': 'That command is not recognised.',
    'invalid_user': 'You are not a recognised user for this bot. Sorry.',
    'recipient_unknown_command': "Sorry, I'm not smart enough to understand. Try looking for the response buttons or "
                                 "just tell me me '{}'.".format(BUTTONS['recipient_request_feel']),
    'recipient_reset': 'What can I help you with?'
}

# Construct the message processing maps.
# These must be defined after the functions themselves, or it generates errors

MESSAGES_ADMIN = {
    BUTTONS['admin_approve_new']: admin_approve_new,
    BUTTONS['admin_approve']: admin_approve,
    BUTTONS['admin_block']: admin_block,
    BUTTONS['admin_confirm_manual']: admin_manual_confirm,
    BUTTONS['admin_reset']: admin_reset,
    BUTTONS['admin_send_feel']: admin_send_feel,
    BUTTONS['admin_send_manual']: admin_send_manual,
    BUTTONS['admin_status']: admin_status,
}
MESSAGES_RECIPIENT = {
    BUTTONS['recipient_request_feel']: recipient_request_feel,
    BUTTONS['recipient_reset']: recipient_reset,
    BUTTONS['recipient_reset_alt']: recipient_reset,
}
STATUS_CUSTOM_MESSAGES = {
    STATE_ADMIN_MANUAL_MESSAGE: admin_manual_message,
}

# Construct the keyboard processing maps.
# As above, defined after the functions to avoid errors

KEYBOARDS_ADMIN = {
    STATE_ADMIN_APPROVE_MESSAGE: keyboard_admin_approval,
    STATE_ADMIN_MANUAL_CONFIRM: keyboard_admin_confirm_manual,
    STATE_ADMIN_MANUAL_MESSAGE: keyboard_empty,
    STATE_ADMIN_STATUS_REQUEST: keyboard_admin_status,
}
KEYBOARDS_RECIPIENT = {

}
