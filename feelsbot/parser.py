import requests

from .message_queue import BUTTON_ADMIN, BUTTON_REQUEST


class MessageParser:
    def __init__(self, config, queue):
        self.config = config
        self.queue = queue

    def process_text_message(self, message):
        func = None
        admin = test_admin(self, message)
        recipient = test_recipient(self, message)

        if not (admin or recipient):
            self.queue.add_message(to=message.from_user, chat_id=message.chat_id, body=body_invalid_user)
            return 200

        if message.body in messages_admin.keys():
            if not admin:
                self.queue.add_message(to=message.from_user, chat_id=message.chat_id, body=body_unrecognised_recipient)
                return 200
            func = messages_admin.get(message.body)

        if message.body in messages_recipient.keys():
            if not recipient:
                self.queue.add_message(to=message.from_user, chat_id=message.chat_id, body=body_unrecognised_admin)
                return 200
            func = messages_recipient.get(message.body)

        if func is None:
            if admin:
                self.queue.add_message(to=message.from_user, chat_id=message.chat_id, body=body_unrecognised_admin)
            else:
                self.queue.add_message(to=message.from_user, chat_id=message.chat_id, body=body_unrecognised_recipient)
            return 200
        else:
            body, status = func(self)
            self.queue.add_message(to=message.from_user, chat_id=message.chat_id, body=body)
            return status


def test_admin(parser, message):
    return parser.config['admin'] == message.from_user


def test_recipient(parser, message):
    return parser.config['recipient'] == message.from_user


def zapier_error_handler(parser, response, source):
    print("Error with posting to Zapier from {}.".format(source))
    print("Full response:\n{}".format(response))
    print("Requesting admin notification.")
    parser.queue.add_message(to=parser.config['admin'],
                             body="Error with request to Zapier. See Apache logs for details.")
    parser.queue.send_all()


def button_admin(parser):
    r = requests.post(parser.config['zaphook'], data={
        'message': 'Someone thought you might be feeling a bit down, so have this message:',
        'noFeels': 'false',
        'source': 'admin'
    })
    if r.status_code == 200:
        return "Processing...", 200
    else:
        zapier_error_handler(parser, r, 'button_admin')
        return "The Zapier request generated an error.", 504


def button_request(parser):
    r = requests.post(parser.config['zaphook'], data={
        'message': 'As requested, another message in case you need more feels:',
        'noFeels': 'false',
        'source': 'recipient'
    })
    if r.status_code == 200:
        return "Waiting for the hamster wheel to reach an appropriate speed...", 200
    else:
        zapier_error_handler(parser, r, 'button_request')
        return "Sorry there's been a problem, please try again later. " \
               "(We're getting more cheese for the hamster right now.)", 504


messages_admin = {
    BUTTON_ADMIN: button_admin
}
messages_recipient = {
    BUTTON_REQUEST: button_request
}

body_invalid_user = 'You are not a recognised user for this bot. Sorry.'
body_unrecognised_admin = 'That command is not recognised.'
body_unrecognised_recipient = "Sorry, I'm not smart enough to understand. Try looking for the response " \
                              "buttons or just tell me me '" + BUTTON_REQUEST + "'."
