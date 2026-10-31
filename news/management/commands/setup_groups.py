from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Create the news application's user groups."""

    help = "Create the Reader, Journalist, and Editor groups."

    def handle(self, *args, **options):
        """Create role groups and assign their content permissions."""

        role_actions = {
            "Reader": ("view",),
            "Journalist": ("view", "add", "change", "delete"),
            "Editor": ("view", "change", "delete"),
        }

        for name, actions in role_actions.items():
            group, _ = Group.objects.get_or_create(name=name)

            permission_names = [
                f"{action}_{model}"
                for model in ("article", "newsletter")
                for action in actions
            ]

            if name == "Editor":
                permission_names.append("add_newsletter")

            permissions = Permission.objects.filter(
                content_type__app_label="news",
                codename__in=permission_names,
            )

            group.permissions.set(permissions)
            self.stdout.write(f"Permissions configured for: {name}")
