"""Utility to generate random password."""
import os
import random
import string


def generate_rand_password(size: int = 8) -> str:
    """Create a random password with letters and digits."""
    random.seed(os.urandom(200))
    chars = string.ascii_letters + string.digits
    password = "".join(random.choice(chars) for i in range(size - 1))
    password += random.choice(string.digits)
    password_list = list(password)
    random.shuffle(password_list)
    result = "".join(password_list)
    return result
