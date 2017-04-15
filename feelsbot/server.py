import json

from flask import Flask, request, Response
from kik import KikApi, Configuration
from kik.messages import messages_from_json, TextMessage

from .message_queue import MessageQueue
from .parser import MessageParser
from .util import bool_from_string


NOTIFY_SOURCES = {
    'unknown': 'Unknown trigger source:',
    'twitter': 'Triggered by lack of twitter:',
    'push': 'Triggered by Zapier push:',
    'admin': 'Triggered by admin request:',
    'recipient': 'Triggered by recipient request:',
    'manual': 'Manual message sent:',
    'schedule': 'Triggered as scheduled:'
}

config = {}
app = Flask(__name__)
kik = None
# Doing initialisation here, so the IDE knows what the objects are
queue = MessageQueue(None, None)
parser = MessageParser(None, None)


def init_app(path):
    """
    Ensure that the configuration file is loaded by the web server before it is given the Flask app.
    :param path: Location of the json configuration file for the application to be run.
    :return: The flask app object, to be used as the WSGI application.
    """
    global config, kik, queue, parser

    with open(path) as config_file:
        config = json.load(config_file)

    kik = KikApi(config['bot_username'], config['bot_api_key'])
    kik.set_configuration(Configuration(webhook=config['webhook']))
    queue = MessageQueue(config, kik)
    parser = MessageParser(config, queue)

    return app


@app.route('/')
def hello_world():
    return 'Hello Developer World!'


@app.route('/incoming', methods=['POST'])
def incoming():
    if not kik.verify_signature(request.headers.get('X-Kik-Signature'), request.get_data()):
        return Response(status=403)

    messages = messages_from_json(request.json['messages'])

    for message in messages:
        if isinstance(message, TextMessage):
            result = parser.process_text_message(message)
            if result != 200:
                qr = queue.send_all()
                if qr != 200:
                    incoming_error_handler(result, qr)
                return Response(status=result)

    # Note the function call to send_all().
    # As per documentation, send_all() returns an appropriate response code based upon success or failure.
    return Response(status=queue.send_all())


@app.route('/message', methods=['POST'])
def from_zapier():
    try:
        auth = request.authorization
        if auth.username != config['webhook_user'] or auth.password != config['webhook_pass']:
            return Response(status=403)
    except AttributeError:
        return Response(status=401)

    post = request.form
    body_message = post['message']
    no_feel = bool_from_string(post['noFeels'])

    try:
        source = post['source']
        body_notify = NOTIFY_SOURCES[source]
    except KeyError:
        body_notify = NOTIFY_SOURCES['unknown']

    if not no_feel:
        feel = u"\n\n{}\n\u00A0  \u2015{} ({})".format(post['feelsComment'], post['from'], post['feelsDate'])
        body_message += feel
        body_notify += feel

    queue.add_message(to=config['admin'], body=body_notify)
    queue.add_message(to=config['recipient'], body=body_message)

    # As above, note the function call to send_all().
    return Response(status=queue.send_all())


# =================================================================================================================

if __name__ == '__main__':
    app.run()

# =================================================================================================================


def incoming_error_handler(parser_result, queue_result):
    """
    Called for error logging if the parser returns an error code and the queue on sending it also returns an error
    :param parser_result:
    :param queue_result:
    :return:
    """
    print("Multiple errors when handling response to /incoming.")
    print("Status code {} from parser, status code {} from sending message queue.".format(parser_result, queue_result))
    print("Sending admin notification.")
    queue.add_message(config['admin'], "Multiple error statuses when processing an incoming server message. "
                                       "See error logs for details.")
    queue.send_all()
