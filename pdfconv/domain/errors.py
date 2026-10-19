class ConversionError(Exception):

class UnsupportedInputError(ConversionError):

class PasswordRequiredError(ConversionError):

class InputTooLargeError(ConversionError):
