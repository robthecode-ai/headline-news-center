from .models import Article, Newsletter


def editable_articles(user):
    """Return articles the user is permitted to manage."""
    if user.groups.filter(name="Editor").exists():
        return Article.objects.filter(
            publisher__editors=user,
        ).distinct()

    if user.groups.filter(name="Journalist").exists():
        return Article.objects.filter(author=user)

    return Article.objects.none()


def editable_newsletters(user):
    """Return newsletters the user is permitted to manage."""
    if user.groups.filter(name="Editor").exists():
        return Newsletter.objects.filter(
            publisher__editors=user,
        ).distinct()

    if user.groups.filter(name="Journalist").exists():
        return Newsletter.objects.filter(author=user)

    return Newsletter.objects.none()


def visible_articles(user):
    """Return published articles within the user's browsing scope."""
    articles = Article.objects.filter(approved=True)

    if (
        user.is_authenticated
        and user.groups.filter(name="Editor").exists()
    ):
        articles = articles.filter(publisher__editors=user)

    return articles.distinct()


def visible_newsletters(user):
    """Return newsletters within the user's browsing scope."""
    newsletters = Newsletter.objects.all()

    if (
        user.is_authenticated
        and user.groups.filter(name="Editor").exists()
    ):
        newsletters = newsletters.filter(publisher__editors=user)

    return newsletters.distinct()
