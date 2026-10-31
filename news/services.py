import logging
from smtplib import SMTPException

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.db.models import Q
from django.urls import reverse
from rest_framework.authtoken.models import Token

from .models import User


logger = logging.getLogger(__name__)


def log_approved_article(article, editor):
    """POST an approved article to our authenticated logging endpoint."""
    token, _ = Token.objects.get_or_create(user=editor)

    response = requests.post(
        settings.NEWS_SITE_URL
        + reverse("news_api:approved_article_log"),
        json={"article_id": article.pk},
        headers={"Authorization": f"Token {token.key}"},
        timeout=5,
        allow_redirects=False,
    )

    if response.status_code not in (200, 201):
        raise requests.RequestException(
            f"Approval logging returned HTTP {response.status_code}."
        )


def email_article_subscribers(article):
    """Submit one email with subscriber addresses hidden in BCC."""
    subscription_filter = Q(subscribed_journalists=article.author)

    if article.publisher_id:
        subscription_filter |= Q(
            subscribed_publishers=article.publisher,
        )

    recipients = list(
        User.objects.filter(
            subscription_filter,
            role="reader",
            is_active=True,
        ).exclude(email="").values_list(
            "email",
            flat=True,
        ).distinct()
    )

    if not recipients:
        return

    article_url = (
        settings.NEWS_SITE_URL
        + reverse("news:article_detail", args=[article.pk])
    )

    subject = " ".join(article.title.splitlines())

    email = EmailMessage(
        subject=f"New article: {subject}",
        body=(
            f"{article.title}\n\n"
            f"By {article.author.username}\n\n"
            f"{article.content}\n\n"
            f"Read online: {article_url}"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        bcc=recipients,
    )

    if email.send(using="default") != 1:
        raise OSError("The email backend did not accept the message.")


def publish_article(article, editor):
    """Approve an article and attempt its outstanding delivery steps."""
    if not article.approved:
        article.approved = True
        article.email_sent = False
        article.api_logged = False
        article.save(
            update_fields=["approved", "email_sent", "api_logged"],
        )

    errors = []

    if not article.api_logged:
        try:
            log_approved_article(article, editor)
        except requests.RequestException:
            logger.exception("Approval API logging failed.")
            errors.append("API logging failed.")
        else:
            article.api_logged = True
            article.save(update_fields=["api_logged"])

    if not article.email_sent:
        try:
            email_article_subscribers(article)
        except (SMTPException, OSError, ValueError):
            logger.exception("Subscriber email failed.")
            errors.append("Subscriber email failed.")
        else:
            article.email_sent = True
            article.save(update_fields=["email_sent"])

    return errors


def email_newsletter_subscribers(newsletter):
    """Email a newly created newsletter to its active subscribers."""
    subscription_filter = Q(
        subscribed_journalists=newsletter.author,
    )

    if newsletter.publisher_id:
        subscription_filter |= Q(
            subscribed_publishers=newsletter.publisher,
        )

    recipients = list(
        User.objects.filter(
            subscription_filter,
            role="reader",
            is_active=True,
        ).exclude(email="").values_list(
            "email",
            flat=True,
        ).distinct()
    )

    if not recipients:
        return

    body = f"{newsletter.title}\n\n{newsletter.description}\n\n"

    for article in newsletter.articles.filter(approved=True):
        article_url = (
            settings.NEWS_SITE_URL
            + reverse("news:article_detail", args=[article.pk])
        )
        body += f"{article.title}\n{article_url}\n\n"

    newsletter_url = (
        settings.NEWS_SITE_URL
        + reverse("news:newsletter_detail", args=[newsletter.pk])
    )
    body += f"View newsletter: {newsletter_url}"

    subject = " ".join(newsletter.title.splitlines())

    email = EmailMessage(
        subject=f"Newsletter: {subject}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        bcc=recipients,
    )

    if email.send(using="default") != 1:
        raise OSError("The email backend did not accept the newsletter.")
