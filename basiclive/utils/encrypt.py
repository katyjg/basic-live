import base64


def encrypt(private):
    public = base64.urlsafe_b64encode(private.encode()).decode()
    return public


def decrypt(public):
    private = base64.urlsafe_b64decode(public.encode()).decode()
    return private