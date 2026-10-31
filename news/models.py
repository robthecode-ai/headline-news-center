from django.contrib.auth.models import AbstractUser
from django.db import models
from django.contrib.auth.models import Group
from django.db import transaction


# Create your models here.
class User(AbstractUser):
    """Represent an account with a news application role."""

    ROLE_CHOICES = [
        ("reader", "Reader"),
        ("journalist", "Journalist"),
        ("editor", "Editor"),
    ]

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default="reader",
    )

    subscribed_publishers = models.ManyToManyField(
        "Publisher",
        related_name="subscribers",
        blank=True,
    )

    subscribed_journalists = models.ManyToManyField(
        "self",
        symmetrical=False,
        related_name="subscribers",
        limit_choices_to={"role": "journalist"},
        blank=True,
    )

    def save(self, *args, **kwargs):
        """Save the user and synchronise their role group."""

        role_groups = {
            "reader": "Reader",
            "journalist": "Journalist",
            "editor": "Editor",
        }

        with transaction.atomic():
            group = Group.objects.get(name=role_groups[self.role])

            super().save(*args, **kwargs)

            previous_groups = Group.objects.filter(
                name__in=role_groups.values(),
            ).exclude(pk=group.pk)

            self.groups.remove(*previous_groups)
            self.groups.add(group)
            self.clear_reader_subscriptions()

    def clear_reader_subscriptions(self):
        """Remove reader-only subscriptions from non-reader accounts."""
        if self.role != "reader":
            self.subscribed_publishers.clear()
            self.subscribed_journalists.clear()


class Publisher(models.Model):
    """Represent a news organisation and its editorial team."""

    name = models.CharField(max_length=200)

    editors = models.ManyToManyField(
        User,
        related_name="editor_publishers",
        limit_choices_to={"role": "editor"},
        blank=True,
    )

    journalists = models.ManyToManyField(
        User,
        related_name="journalist_publishers",
        limit_choices_to={"role": "journalist"},
        blank=True,
    )

    def __str__(self):
        """Return the publisher's name for display."""
        return self.name


class Article(models.Model):
    """Represent a news story submitted for editorial approval."""

    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    approved = models.BooleanField(default=False)
    email_sent = models.BooleanField(default=False)
    api_logged = models.BooleanField(default=False)

    author = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="articles",
        limit_choices_to={"role": "journalist"},
    )

    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.PROTECT,
        related_name="articles",
        null=True,
        blank=True,
    )

    image = models.ImageField(
        upload_to="articles/",
        blank=True,
    )

    caption = models.CharField(
        max_length=300,
        blank=True,
    )

    def __str__(self):
        """Return the article's title for display."""
        return self.title


class Newsletter(models.Model):
    """Represent a curated collection of news articles."""

    title = models.CharField(max_length=200)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    author = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="newsletters",
        limit_choices_to={"role__in": ["journalist", "editor"]},
    )

    publisher = models.ForeignKey(
        Publisher,
        on_delete=models.PROTECT,
        related_name="newsletters",
        null=True,
        blank=True,
    )

    articles = models.ManyToManyField(
        Article,
        related_name="newsletters",
        limit_choices_to={"approved": True},
    )

    def __str__(self):
        """Return the newsletter's title for display."""
        return self.title


class ApprovedArticleLog(models.Model):
    """Store the latest logged publication of an approved article."""

    article = models.OneToOneField(
        Article,
        on_delete=models.CASCADE,
        related_name="approval_log",
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    logged_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        """Return the logged article's title."""
        return self.title
