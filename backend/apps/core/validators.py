from django.core.validators import RegexValidator

# E.164: "+" then 8 to 15 digits, no leading zero in the country code. Kenya: +2547XXXXXXXX.
e164_validator = RegexValidator(
    regex=r"^\+[1-9]\d{7,14}$",
    message="Enter the number in international format, for example +254712345678.",
)
