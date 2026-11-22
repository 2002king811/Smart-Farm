from django.dispatch import Signal

# Sent inside the sign-up transaction with farm=<Farm>, created_by=<User>.
# Later phases connect here to seed defaults: locations and groups (phase 3), activity
# categories (phase 4), notification preferences (phase 6).
farm_created = Signal()
