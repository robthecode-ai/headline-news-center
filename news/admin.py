from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import Article, ApprovedArticleLog, Newsletter, Publisher, User


# Register your models here.
@admin.register(User)
class NewsUserAdmin(UserAdmin):
    """Manage news users and their roles in the admin site."""

    readonly_fields = ("groups",)

    fieldsets = UserAdmin.fieldsets + (
        ("News role", {"fields": ("role",)}),
        (
            "Subscriptions",
            {
                "fields": (
                    "subscribed_publishers",
                    "subscribed_journalists",
                ),
            },
        ),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("News role", {"fields": ("role",)}),
    )

    def save_related(self, request, form, formsets, change):
        """Enforce role-specific subscriptions after related data saves."""
        super().save_related(request, form, formsets, change)
        form.instance.clear_reader_subscriptions()


admin.site.register(Publisher)
admin.site.register(Article)
admin.site.register(Newsletter)
admin.site.register(ApprovedArticleLog)
