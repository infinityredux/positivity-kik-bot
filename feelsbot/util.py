

def bool_from_string(boolean):
    """
    Shortcut (quick and dirty) check if a string is a true or false value.
    :param boolean: String to be evaluated.
    :return: True if the string appears to be true, False otherwise.
    """
    return boolean[0].upper() == 'T'
