from django.db.models import Q

from .models import Article, Newsletter


def editable_articles(user):
    """Return articles the user is permitted to manage."""
    if user.groups.filter(name="Editor").exists():
        return Article.objects.filter(
            Q(publisher__editors=user)
            | Q(publisher__isnull=True),
        ).distinct()

    if user.groups.filter(name="Journalist").exists():
        return Article.objects.filter(author=user)

    return Article.objects.none()


def editable_newsletters(user):
    """Return newsletters the user is permitted to manage."""
    if user.groups.filter(name="Editor").exists():
        return Newsletter.objects.filter(
            Q(publisher__editors=user)
            | Q(publisher__isnull=True),
        ).distinct()

    if user.groups.filter(name="Journalist").exists():
        return Newsletter.objects.filter(author=user)

    return Newsletter.objects.none()
