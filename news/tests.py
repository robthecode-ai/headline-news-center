from unittest.mock import patch

import requests
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import (
    ApprovedArticleLog,
    Article,
    Newsletter,
    Publisher,
    User,
)


@override_settings(
    MAILERS={
        "default": {
            "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
        },
    },
    NEWS_SITE_URL="http://127.0.0.1:8000",
    DEFAULT_FROM_EMAIL="news@example.com",
)
class NewsApplicationTests(TestCase):
    """Test news access, subscriptions, newsletters, and publication."""

    def setUp(self):
        """Create temporary accounts and content before each test."""
        call_command("setup_groups")

        self.password = "Test-passphrase-4826!"

        self.reader = User.objects.create_user(
            username="test_reader",
            email="reader@example.com",
            password=self.password,
            role="reader",
        )
        self.journalist = User.objects.create_user(
            username="test_journalist",
            password=self.password,
            role="journalist",
        )
        self.other_journalist = User.objects.create_user(
            username="other_journalist",
            password=self.password,
            role="journalist",
        )
        self.editor = User.objects.create_user(
            username="test_editor",
            password=self.password,
            role="editor",
        )

        self.publisher = Publisher.objects.create(
            name="First Publisher",
        )
        self.publisher.journalists.add(self.journalist)
        self.publisher.editors.add(self.editor)

        self.other_publisher = Publisher.objects.create(
            name="Other Publisher",
        )
        self.other_publisher.journalists.add(self.other_journalist)

        self.approved_article = Article.objects.create(
            title="Approved story",
            content="An approved story from the first publisher.",
            author=self.journalist,
            publisher=self.publisher,
            approved=True,
            email_sent=True,
            api_logged=True,
        )
        self.pending_article = Article.objects.create(
            title="Pending story",
            content="This story is awaiting approval.",
            author=self.journalist,
            publisher=self.publisher,
        )
        self.other_article = Article.objects.create(
            title="Other publisher story",
            content="An approved story from another publisher.",
            author=self.other_journalist,
            publisher=self.other_publisher,
            approved=True,
        )

        self.reader_token = Token.objects.create(user=self.reader)
        self.journalist_token = Token.objects.create(
            user=self.journalist,
        )
        self.editor_token = Token.objects.create(user=self.editor)

        self.api = APIClient()

    def test_api_requires_authentication(self):
        """Reject article requests without a token."""
        response = self.api.get(reverse("news_api:article_list"))

        self.assertEqual(response.status_code, 401)

    def test_valid_credentials_return_token(self):
        """Return the journalist's token after successful API login."""
        response = self.api.post(
            reverse("news_api:token"),
            {
                "username": self.journalist.username,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["token"],
            self.journalist_token.key,
        )

    def test_wrong_password_is_rejected(self):
        """Reject incorrect API login credentials."""
        response = self.api.post(
            reverse("news_api:token"),
            {
                "username": self.journalist.username,
                "password": "Incorrect-password!",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("token", response.data)

    def test_article_list_shows_only_approved_stories(self):
        """Exclude pending articles from the general API list."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.reader_token.key}",
        )

        response = self.api.get(reverse("news_api:article_list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 2)
        self.assertContains(response, self.approved_article.title)
        self.assertContains(response, self.other_article.title)
        self.assertNotContains(response, self.pending_article.title)

    def test_pending_article_detail_is_hidden(self):
        """Reject direct API access to pending content."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.reader_token.key}",
        )

        response = self.api.get(
            reverse(
                "news_api:article_detail",
                args=[self.pending_article.pk],
            ),
        )

        self.assertEqual(response.status_code, 404)

    def test_publisher_subscription_returns_matching_content(self):
        """Return approved stories from the followed publisher."""
        self.reader.subscribed_publishers.add(self.publisher)
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.reader_token.key}",
        )

        response = self.api.get(
            reverse("news_api:subscribed_articles"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["id"],
            self.approved_article.pk,
        )

    def test_journalist_subscription_returns_matching_content(self):
        """Return approved stories from the followed journalist."""
        self.reader.subscribed_journalists.add(self.journalist)
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.reader_token.key}",
        )

        response = self.api.get(
            reverse("news_api:subscribed_articles"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["id"],
            self.approved_article.pk,
        )

    def test_overlapping_subscriptions_do_not_duplicate_stories(self):
        """Return a story once when author and publisher both match."""
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.subscribed_journalists.add(self.journalist)
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.reader_token.key}",
        )

        response = self.api.get(
            reverse("news_api:subscribed_articles"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["id"],
            self.approved_article.pk,
        )

    def test_no_subscriptions_returns_empty_feed(self):
        """Return no subscribed stories when the reader follows nobody."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.reader_token.key}",
        )

        response = self.api.get(
            reverse("news_api:subscribed_articles"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_journalist_creates_pending_article(self):
        """Assign ownership and prevent self-approval through API input."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.journalist_token.key}",
        )

        response = self.api.post(
            reverse("news_api:article_list"),
            {
                "title": "New API story",
                "content": "Submitted through the API.",
                "publisher": None,
                "author": self.other_journalist.pk,
                "approved": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        article = Article.objects.get(pk=response.data["id"])
        self.assertEqual(article.author, self.journalist)
        self.assertFalse(article.approved)

    def test_invalid_article_is_rejected(self):
        """Reject an empty headline without creating a record."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.journalist_token.key}",
        )

        response = self.api.post(
            reverse("news_api:article_list"),
            {"title": "", "content": "A story without a headline."},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Article.objects.count(), 3)

    def test_journalist_cannot_assign_another_publisher(self):
        """Reject publisher membership bypass attempts."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.journalist_token.key}",
        )

        response = self.api.post(
            reverse("news_api:article_list"),
            {
                "title": "Wrong publisher",
                "content": "This assignment should be rejected.",
                "publisher": self.other_publisher.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Article.objects.count(), 3)

    def test_reader_cannot_create_update_or_delete(self):
        """Enforce read-only API access for readers."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.reader_token.key}",
        )
        detail_url = reverse(
            "news_api:article_detail",
            args=[self.approved_article.pk],
        )
        data = {
            "title": "Unauthorised change",
            "content": "A reader must not save this.",
            "publisher": None,
        }

        create_response = self.api.post(
            reverse("news_api:article_list"),
            data,
            format="json",
        )
        update_response = self.api.put(
            detail_url,
            data,
            format="json",
        )
        delete_response = self.api.delete(detail_url)

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(update_response.status_code, 403)
        self.assertEqual(delete_response.status_code, 403)
        self.assertEqual(Article.objects.count(), 3)

        self.approved_article.refresh_from_db()
        self.assertEqual(self.approved_article.title, "Approved story")

    def test_editing_own_article_resets_publication(self):
        """Require reapproval and delivery after an article changes."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.journalist_token.key}",
        )

        response = self.api.put(
            reverse(
                "news_api:article_detail",
                args=[self.approved_article.pk],
            ),
            {
                "title": "Revised story",
                "content": "Updated content.",
                "publisher": self.publisher.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        self.approved_article.refresh_from_db()
        self.assertEqual(self.approved_article.title, "Revised story")
        self.assertEqual(
            self.approved_article.author,
            self.journalist,
        )
        self.assertFalse(self.approved_article.approved)
        self.assertFalse(self.approved_article.email_sent)
        self.assertFalse(self.approved_article.api_logged)

    def test_journalist_cannot_manage_another_authors_article(self):
        """Reject updates and deletion outside the author's ownership."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.journalist_token.key}",
        )
        url = reverse(
            "news_api:article_detail",
            args=[self.other_article.pk],
        )

        update_response = self.api.put(
            url,
            {"title": "Unauthorised", "content": "Rejected."},
            format="json",
        )
        delete_response = self.api.delete(url)

        self.assertEqual(update_response.status_code, 404)
        self.assertEqual(delete_response.status_code, 404)

        self.other_article.refresh_from_db()
        self.assertEqual(
            self.other_article.title,
            "Other publisher story",
        )

    def test_editor_deletion_respects_publisher_membership(self):
        """Allow own-publisher deletion and reject another publisher."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.editor_token.key}",
        )

        rejected = self.api.delete(
            reverse(
                "news_api:article_detail",
                args=[self.other_article.pk],
            ),
        )
        allowed = self.api.delete(
            reverse(
                "news_api:article_detail",
                args=[self.approved_article.pk],
            ),
        )

        self.assertEqual(rejected.status_code, 404)
        self.assertEqual(allowed.status_code, 204)
        self.assertTrue(
            Article.objects.filter(pk=self.other_article.pk).exists(),
        )
        self.assertFalse(
            Article.objects.filter(
                pk=self.approved_article.pk,
            ).exists(),
        )

    @patch("news.services.requests.post")
    def test_editor_approval_delivers_once(self, mock_post):
        """Approve, submit email, and avoid ordinary repeat delivery."""
        mock_post.return_value.status_code = 201
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.subscribed_journalists.add(self.journalist)
        self.client.force_login(self.editor)
        url = reverse(
            "news:article_approve",
            args=[self.pending_article.pk],
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.pending_article.refresh_from_db()
        self.assertTrue(self.pending_article.approved)
        self.assertTrue(self.pending_article.api_logged)
        self.assertTrue(self.pending_article.email_sent)

        mock_post.assert_called_once_with(
            "http://127.0.0.1:8000/api/approved/",
            json={"article_id": self.pending_article.pk},
            headers={
                "Authorization": f"Token {self.editor_token.key}",
            },
            timeout=5,
            allow_redirects=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, [self.reader.email])
        self.assertEqual(mail.outbox[0].to, [])
        self.assertIn(
            self.pending_article.content,
            mail.outbox[0].body,
        )

        repeated = self.client.post(url)

        self.assertEqual(repeated.status_code, 302)
        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual(len(mail.outbox), 1)

    @patch("news.services.requests.post")
    def test_failed_api_delivery_can_retry_without_repeating_email(
        self,
        mock_post,
    ):
        """Retry failed logging while preserving completed email delivery."""
        mock_post.side_effect = requests.RequestException(
            "Simulated connection failure",
        )
        self.reader.subscribed_journalists.add(self.journalist)
        self.client.force_login(self.editor)
        url = reverse(
            "news:article_approve",
            args=[self.pending_article.pk],
        )

        with self.assertLogs("news.services", level="ERROR"):
            response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        self.pending_article.refresh_from_db()
        self.assertTrue(self.pending_article.approved)
        self.assertFalse(self.pending_article.api_logged)
        self.assertTrue(self.pending_article.email_sent)
        self.assertEqual(len(mail.outbox), 1)

        mock_post.side_effect = None
        mock_post.return_value.status_code = 200

        retried = self.client.post(url)

        self.assertEqual(retried.status_code, 302)
        self.pending_article.refresh_from_db()
        self.assertTrue(self.pending_article.api_logged)
        self.assertEqual(mock_post.call_count, 2)
        self.assertEqual(len(mail.outbox), 1)

    @patch("news.services.requests.post")
    def test_wrong_publisher_editor_cannot_approve(self, mock_post):
        """Reject approval outside the editor's publisher membership."""
        self.other_article.approved = False
        self.other_article.save()
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "news:article_approve",
                args=[self.other_article.pk],
            ),
        )

        self.assertEqual(response.status_code, 404)
        self.other_article.refresh_from_db()
        self.assertFalse(self.other_article.approved)
        mock_post.assert_not_called()
        self.assertEqual(len(mail.outbox), 0)

    @patch("news.services.requests.post")
    def test_reader_and_journalist_cannot_approve(self, mock_post):
        """Restrict the approval action to editors."""
        url = reverse(
            "news:article_approve",
            args=[self.pending_article.pk],
        )

        self.client.force_login(self.reader)
        reader_response = self.client.post(url)

        self.client.force_login(self.journalist)
        journalist_response = self.client.post(url)

        self.assertEqual(reader_response.status_code, 403)
        self.assertEqual(journalist_response.status_code, 403)
        self.pending_article.refresh_from_db()
        self.assertFalse(self.pending_article.approved)
        mock_post.assert_not_called()

    def test_approval_log_does_not_duplicate_records(self):
        """Create one publication log and update it on repeat requests."""
        self.api.credentials(
            HTTP_AUTHORIZATION=f"Token {self.editor_token.key}",
        )
        url = reverse("news_api:approved_article_log")
        data = {"article_id": self.approved_article.pk}

        first = self.api.post(url, data, format="json")
        second = self.api.post(url, data, format="json")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(ApprovedArticleLog.objects.count(), 1)

        log = ApprovedArticleLog.objects.get(
            article=self.approved_article,
        )
        self.assertEqual(log.title, self.approved_article.title)
        self.assertEqual(log.content, self.approved_article.content)

    def test_newsletter_excludes_pending_stories(self):
        """Keep unapproved content hidden inside a newsletter."""
        newsletter = Newsletter.objects.create(
            title="Weekly newsletter",
            description="A collection of stories.",
            author=self.journalist,
        )
        newsletter.articles.add(
            self.approved_article,
            self.pending_article,
        )

        response = self.client.get(
            reverse(
                "news:newsletter_detail",
                args=[newsletter.pk],
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.approved_article.title)
        self.assertNotContains(response, self.pending_article.title)

    def test_reader_cannot_edit_or_delete_newsletter(self):
        """Reject direct newsletter-management requests from readers."""
        newsletter = Newsletter.objects.create(
            title="Protected newsletter",
            description="Original description.",
            author=self.journalist,
        )
        self.client.force_login(self.reader)

        edited = self.client.post(
            reverse("news:newsletter_edit", args=[newsletter.pk]),
            {"title": "Unauthorised change"},
        )
        deleted = self.client.post(
            reverse("news:newsletter_delete", args=[newsletter.pk]),
        )

        self.assertEqual(edited.status_code, 404)
        self.assertEqual(deleted.status_code, 404)

        newsletter.refresh_from_db()
        self.assertEqual(newsletter.title, "Protected newsletter")

    def test_role_change_clears_reader_subscriptions(self):
        """Remove reader-only subscriptions when promoting an account."""
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.subscribed_journalists.add(self.journalist)

        self.reader.role = "journalist"
        self.reader.save()

        self.reader.refresh_from_db()
        self.assertFalse(self.reader.subscribed_publishers.exists())
        self.assertFalse(self.reader.subscribed_journalists.exists())
        self.assertTrue(
            self.reader.groups.filter(name="Journalist").exists(),
        )

    def test_saving_reader_preserves_subscriptions(self):
        """Keep subscriptions when the account remains a reader."""
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.subscribed_journalists.add(self.journalist)

        self.reader.save()

        self.reader.refresh_from_db()
        self.assertTrue(
            self.reader.subscribed_publishers.filter(
                pk=self.publisher.pk,
            ).exists(),
        )
        self.assertTrue(
            self.reader.subscribed_journalists.filter(
                pk=self.journalist.pk,
            ).exists(),
        )

    def test_editor_management_list_respects_publisher_access(self):
        """List permitted approved and pending articles for an editor."""
        independent = Article.objects.create(
            title="Independent submission",
            content="An independent story.",
            author=self.other_journalist,
        )
        self.client.force_login(self.editor)

        response = self.client.get(reverse("news:manage_articles"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.approved_article.title)
        self.assertContains(response, self.pending_article.title)
        self.assertContains(response, independent.title)
        self.assertNotContains(response, self.other_article.title)

    def test_reader_cannot_open_editor_management_list(self):
        """Reject reader access to the editorial management page."""
        self.client.force_login(self.reader)

        response = self.client.get(reverse("news:manage_articles"))

        self.assertEqual(response.status_code, 403)

    def test_newsletter_creation_emails_subscribers_once(self):
        """Email new newsletters without resending ordinary edits."""
        self.reader.subscribed_publishers.add(self.publisher)
        self.reader.subscribed_journalists.add(self.journalist)
        self.client.force_login(self.journalist)

        response = self.client.post(
            reverse("news:newsletter_create"),
            {
                "title": "Subscriber newsletter",
                "description": "This week's approved stories.",
                "publisher": self.publisher.pk,
                "articles": [self.approved_article.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        newsletter = Newsletter.objects.get(
            title="Subscriber newsletter",
        )
        self.assertEqual(newsletter.author, self.journalist)
        self.assertTrue(
            newsletter.articles.filter(
                pk=self.approved_article.pk,
            ).exists(),
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].bcc, [self.reader.email])
        self.assertIn(newsletter.description, mail.outbox[0].body)
        self.assertIn(
            self.approved_article.title,
            mail.outbox[0].body,
        )

        edited = self.client.post(
            reverse("news:newsletter_edit", args=[newsletter.pk]),
            {
                "title": "Updated newsletter",
                "description": "An updated description.",
                "publisher": self.publisher.pk,
                "articles": [self.approved_article.pk],
            },
        )

        self.assertEqual(edited.status_code, 302)
        newsletter.refresh_from_db()
        self.assertEqual(newsletter.title, "Updated newsletter")
        self.assertEqual(len(mail.outbox), 1)

    def test_homepage_features_latest_approved_article(self):
        """Feature the newest approved story without duplicating it."""
        response = self.client.get(reverse("news:home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["featured_article"],
            self.other_article,
        )
        self.assertEqual(
            list(response.context["latest_articles"]),
            [self.approved_article],
        )
        self.assertNotContains(response, self.pending_article.title)

    def test_homepage_handles_no_articles(self):
        """Display the empty state when no articles exist."""
        Article.objects.all().delete()

        response = self.client.get(reverse("news:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No articles have been published yet.",
        )

    def test_editor_can_register_without_admin_access(self):
        """Create an Editor account through public registration."""
        response = self.client.post(
            reverse("news:register"),
            {
                "username": "new_editor",
                "email": "editor@example.com",
                "role": "editor",
                "password1": self.password,
                "password2": self.password,
            },
        )

        self.assertRedirects(response, reverse("news:login"))

        user = User.objects.get(username="new_editor")
        self.assertEqual(user.role, "editor")
        self.assertTrue(user.groups.filter(name="Editor").exists())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.check_password(self.password))

    def test_registration_ignores_admin_privilege_fields(self):
        """Prevent signup input from granting Django admin privileges."""
        response = self.client.post(
            reverse("news:register"),
            {
                "username": "new_journalist",
                "email": "journalist@example.com",
                "role": "journalist",
                "password1": self.password,
                "password2": self.password,
                "is_staff": True,
                "is_superuser": True,
                "groups": [self.editor.groups.get(name="Editor").pk],
            },
        )

        self.assertRedirects(response, reverse("news:login"))

        user = User.objects.get(username="new_journalist")
        self.assertEqual(user.role, "journalist")
        self.assertTrue(user.groups.filter(name="Journalist").exists())
        self.assertFalse(user.groups.filter(name="Editor").exists())
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_editor_can_create_publisher(self):
        """Add the creating editor to the new publisher."""
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse("news:publisher_create"),
            {"name": "New Publisher"},
        )

        self.assertRedirects(
            response,
            reverse("news:my_publishers"),
        )

        publisher = Publisher.objects.get(name="New Publisher")
        self.assertTrue(
            publisher.editors.filter(pk=self.editor.pk).exists()
        )

    def test_non_editors_cannot_create_publishers(self):
        """Reject publisher creation by readers and journalists."""
        for user in (self.reader, self.journalist):
            with self.subTest(role=user.role):
                self.client.force_login(user)

                response = self.client.post(
                    reverse("news:publisher_create"),
                    {"name": "Unauthorised Publisher"},
                )

                self.assertEqual(response.status_code, 403)

        self.assertFalse(
            Publisher.objects.filter(
                name="Unauthorised Publisher"
            ).exists()
        )

    def test_my_publishers_shows_only_editors_publishers(self):
        """Exclude publishers the current editor does not manage."""
        self.client.force_login(self.editor)

        response = self.client.get(
            reverse("news:my_publishers"),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.publisher.name)
        self.assertNotContains(response, self.other_publisher.name)

    def test_non_editors_cannot_view_my_publishers(self):
        """Restrict publisher management to editors."""
        for user in (self.reader, self.journalist):
            with self.subTest(role=user.role):
                self.client.force_login(user)

                response = self.client.get(
                    reverse("news:my_publishers"),
                )

                self.assertEqual(response.status_code, 403)

    def test_editor_can_update_own_publisher_team(self):
        """Assign a journalist through the application."""
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "news:publisher_team",
                args=[self.publisher.pk],
            ),
            {
                "editors": [self.editor.pk],
                "journalists": [
                    self.journalist.pk,
                    self.other_journalist.pk,
                ],
            },
        )

        self.assertRedirects(
            response,
            reverse("news:my_publishers"),
        )
        self.assertTrue(
            self.publisher.journalists.filter(
                pk=self.other_journalist.pk,
            ).exists()
        )

    def test_editor_cannot_manage_another_publisher_team(self):
        """Prevent changes outside the editor's publishers."""
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "news:publisher_team",
                args=[self.other_publisher.pk],
            ),
            {
                "editors": [self.editor.pk],
                "journalists": [self.journalist.pk],
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            self.other_publisher.editors.filter(
                pk=self.editor.pk,
            ).exists()
        )
        self.assertFalse(
            self.other_publisher.journalists.filter(
                pk=self.journalist.pk,
            ).exists()
        )

    def test_publisher_team_rejects_wrong_role(self):
        """Reject a reader submitted as a journalist."""
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "news:publisher_team",
                args=[self.publisher.pk],
            ),
            {
                "editors": [self.editor.pk],
                "journalists": [self.reader.pk],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "journalists",
            response.context["form"].errors,
        )
        self.assertFalse(
            self.publisher.journalists.filter(
                pk=self.reader.pk,
            ).exists()
        )

    def test_editor_cannot_remove_their_own_membership(self):
        """Preserve the managing editor's access."""
        self.client.force_login(self.editor)

        response = self.client.post(
            reverse(
                "news:publisher_team",
                args=[self.publisher.pk],
            ),
            {
                "editors": [],
                "journalists": [self.journalist.pk],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Keep yourself selected as an editor.",
        )
        self.assertTrue(
            self.publisher.editors.filter(
                pk=self.editor.pk,
            ).exists()
        )

    def test_non_editors_cannot_manage_publisher_team(self):
        """Reject team changes from readers and journalists."""
        for user in (self.reader, self.journalist):
            with self.subTest(role=user.role):
                self.client.force_login(user)

                response = self.client.post(
                    reverse(
                        "news:publisher_team",
                        args=[self.publisher.pk],
                    ),
                    {
                        "editors": [],
                        "journalists": [],
                    },
                )

                self.assertEqual(response.status_code, 403)

        self.assertTrue(
            self.publisher.editors.filter(
                pk=self.editor.pk,
            ).exists()
        )
        self.assertTrue(
            self.publisher.journalists.filter(
                pk=self.journalist.pk,
            ).exists()
        )
