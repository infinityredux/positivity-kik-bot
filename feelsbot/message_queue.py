from kik import KikError
from kik.messages import TextMessage, SuggestedResponseKeyboard, TextResponse


BUTTON_REQUEST = 'Get more feels'
BUTTON_ADMIN = 'Send feels'


class MessageQueue:
    def __init__(self, config, kik):
        self.config = config
        self.kik = kik
        self.queue = {}

    def add_message(self, to, body, chat_id=None):
        """
        ???
        :param to:
        :param body:
        :param chat_id:
        :return:
        """
        if chat_id is not None:
            message = TextMessage(
                to=to,
                chat_id=chat_id,
                body=body
            )
        else:
            message = TextMessage(
                to=to,
                body=body
            )

        # Original version raised error if non-recipient and non-admin user contacted.
        # That is not correct, because we do have a default reply for these cases.
        # Additionally, admin user who is also recipient will get both keyboards - useful for testing.
        keyboards = []
        if to == self.config['recipient']:
            keyboards += keyboard_recipient()
        if to == self.config['admin']:
            keyboards += keyboard_admin()
        build_keyboard(message, to, keyboards)

        try:
            self.queue[to].append(message)
        except KeyError:
            self.queue[to] = [message]

    def send_all(self):
        """
        Send all messages within the queue and make the queue empty again
        :return: 200 if successful, 202 if kik returned an error (based upon http status codes)
        """
        queue = self.queue
        count = {}
        self.queue = {}
        for person in queue.keys():
            count[person] = 0

        # Function within a function
        # For use with the while loop, to save have to do these tests within the loop itself (looks messy)
        def count_unprocessed():
            result = False
            for c in count:
                if count[c] < len(queue[c]):
                    result = True
            return result

        while count_unprocessed():
            sending = []
            for person in queue:
                # Should never exceed 25, but playing safe in case of other errors
                if len(sending) >= 25:
                    break

                add = min(5, 25-len(sending))
                if count[person] < len(queue[person]):
                    # Add the next messages by getting the appropriate splice of the queue
                    # Based upon rate limit of 5 messages per person, 25 messages per batch
                    sending += queue[person][count[person]:count[person] + add]
                    count[person] += add

            # Be certain there is actually something to send
            if len(sending) > 0:
                try:
                    self.kik.send_messages(sending)
                except KikError as e:
                    # Log the error, will appear in apache error logs when running under wsgi
                    error_handler(self, e, queue, count, sending)
                    # Also need to make certain we don't cause Kik server to go into a loop of resending the message
                    # Returning 500 would cause the message to be resent up to a total of 4 times.
                    # Hence 202 is a received and being processed but no guarantee of any outcome.
                    #
                    # NOTE: returning 202 has not actually been tested yet (to confirm it doesn't cause loop).
                    # Other option might be to return 504 instead.
                    return 202

        return 200


def error_handler(message_queue, e, queue, count, sending):
    print("Error encountered during message sending.")
    print("Sending list length: {}".format(len(sending)))
    print("Queue: {}".format(queue))
    print("Count: {}".format(count))
    print("Sending: {}". format(sending))
    print(e)
    try:
        message_queue.kik.send_messages(TextMessage(
            to=message_queue.config['admin'],
            body="Error encountered during message send. See apache logs for details."
        ))
        print("Admin notification sent.")
    except KikError:
        print("Admin notify failed.")


def build_keyboard(message, to, responses):
    """
    Build the keyboard for the provided message with the specified responses.
    :param message: The message to have the responses added to it.
    :param to: The recipient of the message.
    :param responses: An array with Kik keyboard responses.
    :return: Nothing (message object directly modified to include the keyboard)
    """
    if len(responses) > 0:
        message.keyboards.append(
            SuggestedResponseKeyboard(
                to=to,
                hidden=False,
                responses=responses
            )
        )


def keyboard_admin():
    """
    Create keyboard responses that are sent to an admin user.
    :return: An array with the responses that should be sent on the present message.
    """
    return [TextResponse(BUTTON_ADMIN)]


def keyboard_recipient():
    """
    Create keyboard responses that are sent to a message recipient.
    :return: An array with the responses that should be sent on the present message.
    """
    return [TextResponse(BUTTON_REQUEST)]
