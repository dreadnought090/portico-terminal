"""Email inbox poller — auto-detect broker transaction emails.

Independent module. Env-gated: only runs if EMAIL_USER + EMAIL_APP_PASSWORD set.
Polls IMAP for new messages from configured broker senders, parses via Claude
into structured transactions, dispatches confirmation DM via Ginger bot.

On user-confirm → applies to PortfolioItem.

NOT auto-write — confirmation REQUIRED.
"""
from backend.email_inbox.cron import register_cron, scan_new_emails
from backend.email_inbox.recorder import apply_transaction, reject_transaction

__all__ = ["register_cron", "scan_new_emails", "apply_transaction", "reject_transaction"]
