from django.shortcuts import get_object_or_404, redirect, render

from .models import Article, Newsletter, Publisher
from .forms import (
    ArticleForm,
    NewsletterForm,
    PublisherForm,
    PublisherTeamForm,
    RegistrationForm,
    SubscriptionForm,
)
from .permissions import editable_articles, editable_newsletters
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.db.models import Q
from django.views.decorators.http import require_POST
from django.contrib import messages

from .services import email_newsletter_subscribers, publish_article
from smtplib import SMTPException


def home(request):
    """Feature the newest approved story and list recent articles."""
    articles = Article.objects.filter(
        approved=True,
    ).select_related(
        "author",
        "publisher",
    ).order_by("-created_at", "-pk")

    featured_article = articles.first()

    if featured_article:
        latest_articles = articles.exclude(
            pk=featured_article.pk,
        )[:8]
    else:
        latest_articles = articles.none()

    return render(
        request,
        "news/home.html",
        {
            "featured_article": featured_article,
            "latest_articles": latest_articles,
        },
    )


def article_detail(request, pk):
    """Display one approved article or return a 404 response."""
    article = get_object_or_404(
        Article,
        pk=pk,
        approved=True,
    )

    return render(
        request,
        "news/article_detail.html",
        {"article": article},
    )


def register(request):
    """Create an account with the selected application role."""

    if request.method == "POST":
        form = RegistrationForm(request.POST)

        if form.is_valid():
            form.save()
            return redirect("news:login")
    else:
        form = RegistrationForm()

    return render(
        request,
        "news/register.html",
        {"form": form},
    )


@login_required
def my_articles(request):
    """Display the logged-in journalist's articles."""
    if not request.user.groups.filter(name="Journalist").exists():
        return HttpResponseForbidden("Journalists only.")

    articles = Article.objects.filter(
        author=request.user,
    ).order_by("-created_at")

    return render(
        request,
        "news/my_articles.html",
        {"articles": articles},
    )


@login_required
def review_queue(request):
    """Display pending articles this editor is allowed to review."""
    if not request.user.groups.filter(name="Editor").exists():
        return HttpResponseForbidden("Editors only.")

    articles = Article.objects.filter(
        Q(publisher__editors=request.user)
        | Q(publisher__isnull=True),
        approved=False,
    ).distinct().order_by("-created_at")

    return render(
        request,
        "news/review_queue.html",
        {"articles": articles},
    )


@login_required
def article_create(request):
    """Allow a journalist to submit an article for approval."""
    if not request.user.groups.filter(name="Journalist").exists():
        return HttpResponseForbidden("Journalists only.")

    if request.method == "POST":
        form = ArticleForm(
            request.POST,
            request.FILES,
            user=request.user,
        )

        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.approved = False
            article.save()
            return redirect("news:my_articles")
    else:
        form = ArticleForm(user=request.user)

    return render(
        request,
        "news/article_form.html",
        {"form": form, "page_title": "Write article"},
    )


@login_required
def article_edit(request, pk):
    """Update an authorised article and require editorial reapproval."""
    article = get_object_or_404(
        editable_articles(request.user),
        pk=pk,
    )

    if request.method == "POST":
        form = ArticleForm(
            request.POST,
            request.FILES,
            instance=article,
            user=request.user,
        )

        if form.is_valid():
            article = form.save(commit=False)
            article.approved = False
            article.email_sent = False
            article.api_logged = False
            article.save()

            if request.user.role == "editor":
                return redirect("news:review_queue")

            return redirect("news:my_articles")
    else:
        form = ArticleForm(
            instance=article,
            user=request.user,
        )

    return render(
        request,
        "news/article_form.html",
        {"form": form, "page_title": "Edit article"},
    )


@login_required
def article_review(request, pk):
    """Display an article this editor is authorised to review."""
    if not request.user.groups.filter(name="Editor").exists():
        return HttpResponseForbidden("Editors only.")

    article = get_object_or_404(
        editable_articles(request.user),
        pk=pk,
    )

    return render(
        request,
        "news/article_review.html",
        {"article": article},
    )


@login_required
@require_POST
def article_approve(request, pk):
    """Approve authorised content and report publication results."""
    if not request.user.groups.filter(name="Editor").exists():
        return HttpResponseForbidden("Editors only.")

    article = get_object_or_404(
        editable_articles(request.user),
        pk=pk,
    )

    errors = publish_article(article, request.user)

    if errors:
        messages.warning(
            request,
            "Article approved, but "
            + " ".join(errors)
            + " Use Retry publication to retry unfinished steps.",
        )
        return redirect("news:article_review", pk=article.pk)

    messages.success(
        request,
        "Article approved. API logging and subscriber notification "
        "processing are complete.",
    )
    return redirect("news:review_queue")


@login_required
def article_delete(request, pk):
    """Delete an authorised article after POST confirmation."""
    article = get_object_or_404(
        editable_articles(request.user),
        pk=pk,
    )

    if request.method == "POST":
        article.delete()

        if request.user.role == "editor":
            return redirect("news:review_queue")

        return redirect("news:my_articles")

    return render(
        request,
        "news/article_confirm_delete.html",
        {"article": article},
    )


@login_required
def subscriptions(request):
    """Allow a reader to update their own subscriptions."""
    if not request.user.groups.filter(name="Reader").exists():
        return HttpResponseForbidden("Readers only.")

    if request.method == "POST":
        form = SubscriptionForm(
            request.POST,
            instance=request.user,
        )

        if form.is_valid():
            form.save()
            return redirect("news:subscribed_articles")
    else:
        form = SubscriptionForm(instance=request.user)

    return render(
        request,
        "news/subscriptions.html",
        {"form": form},
    )


@login_required
def subscribed_articles(request):
    """Display approved articles matching the reader's subscriptions."""
    if not request.user.groups.filter(name="Reader").exists():
        return HttpResponseForbidden("Readers only.")

    articles = Article.objects.filter(
        Q(publisher__in=request.user.subscribed_publishers.all())
        | Q(author__in=request.user.subscribed_journalists.all()),
        approved=True,
    ).distinct().order_by("-created_at")

    return render(
        request,
        "news/subscribed_articles.html",
        {"articles": articles},
    )


def newsletter_list(request):
    """Display available newsletters, newest first."""
    newsletters = Newsletter.objects.select_related(
        "author",
        "publisher",
    ).order_by("-created_at")

    return render(
        request,
        "news/newsletter_list.html",
        {"newsletters": newsletters},
    )


def newsletter_detail(request, pk):
    """Display a newsletter and its currently approved articles."""
    newsletter = get_object_or_404(Newsletter, pk=pk)
    articles = newsletter.articles.filter(
        approved=True,
    ).order_by("-created_at")

    can_manage = (
        request.user.is_authenticated
        and editable_newsletters(request.user).filter(
            pk=newsletter.pk,
        ).exists()
    )

    return render(
        request,
        "news/newsletter_detail.html",
        {
            "newsletter": newsletter,
            "articles": articles,
            "can_manage": can_manage,
        },
    )


@login_required
def newsletter_create(request):
    """Allow journalists and editors to create newsletters."""
    if not request.user.groups.filter(
        name__in=("Journalist", "Editor"),
    ).exists():
        return HttpResponseForbidden("Journalists and editors only.")

    if request.method == "POST":
        form = NewsletterForm(
            request.POST,
            user=request.user,
        )

        if form.is_valid():
            newsletter = form.save(commit=False)
            newsletter.author = request.user
            newsletter.save()
            form.save_m2m()
            try:
                email_newsletter_subscribers(newsletter)
            except (SMTPException, OSError, ValueError):
                messages.warning(
                    request,
                    "Newsletter created, but its email notification failed.",
                )
            return redirect(
                "news:newsletter_detail",
                pk=newsletter.pk,
            )
    else:
        form = NewsletterForm(user=request.user)

    return render(
        request,
        "news/newsletter_form.html",
        {"form": form, "page_title": "Create newsletter"},
    )


@login_required
def newsletter_edit(request, pk):
    """Update a newsletter within the user's permitted scope."""
    newsletter = get_object_or_404(
        editable_newsletters(request.user),
        pk=pk,
    )

    if request.method == "POST":
        form = NewsletterForm(
            request.POST,
            instance=newsletter,
            user=request.user,
        )

        if form.is_valid():
            newsletter = form.save()
            return redirect(
                "news:newsletter_detail",
                pk=newsletter.pk,
            )
    else:
        form = NewsletterForm(
            instance=newsletter,
            user=request.user,
        )

    return render(
        request,
        "news/newsletter_form.html",
        {"form": form, "page_title": "Edit newsletter"},
    )


@login_required
def newsletter_delete(request, pk):
    """Delete an authorised newsletter after POST confirmation."""
    newsletter = get_object_or_404(
        editable_newsletters(request.user),
        pk=pk,
    )

    if request.method == "POST":
        newsletter.delete()
        return redirect("news:newsletter_list")

    return render(
        request,
        "news/newsletter_confirm_delete.html",
        {"newsletter": newsletter},
    )


@login_required
def manage_articles(request):
    """List all articles within the editor's permitted scope."""
    if not request.user.groups.filter(name="Editor").exists():
        return HttpResponseForbidden("Editors only.")

    articles = editable_articles(request.user).select_related(
        "author",
        "publisher",
    ).order_by("-created_at")

    return render(
        request,
        "news/manage_articles.html",
        {"articles": articles},
    )


@login_required
def publisher_create(request):
    """Create a publisher and associate the current editor."""
    if not request.user.groups.filter(name="Editor").exists():
        return HttpResponseForbidden("Editors only.")

    if request.method == "POST":
        form = PublisherForm(request.POST)

        if form.is_valid():
            publisher = form.save()
            publisher.editors.add(request.user)

            messages.success(request, "Publisher created.")
            return redirect("news:my_publishers")
    else:
        form = PublisherForm()

    return render(
        request,
        "news/publisher_form.html",
        {"form": form},
    )


@login_required
def my_publishers(request):
    """List publishers managed by the current editor."""
    if not request.user.groups.filter(name="Editor").exists():
        return HttpResponseForbidden("Editors only.")

    publishers = Publisher.objects.filter(
        editors=request.user,
    ).order_by("name")

    return render(
        request,
        "news/my_publishers.html",
        {"publishers": publishers},
    )


@login_required
def publisher_team(request, pk):
    """Manage a team only when the current editor belongs to it."""
    if not request.user.groups.filter(name="Editor").exists():
        return HttpResponseForbidden("Editors only.")

    publisher = get_object_or_404(
        Publisher,
        pk=pk,
        editors=request.user,
    )

    if request.method == "POST":
        form = PublisherTeamForm(
            request.POST,
            instance=publisher,
            user=request.user,
        )

        if form.is_valid():
            form.save()
            messages.success(request, "Publisher team updated.")
            return redirect("news:my_publishers")
    else:
        form = PublisherTeamForm(
            instance=publisher,
            user=request.user,
        )

    return render(
        request,
        "news/publisher_team.html",
        {
            "form": form,
            "publisher": publisher,
        },
    )
