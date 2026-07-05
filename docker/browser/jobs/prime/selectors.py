"""ALL Prime/Okta selectors live here and ONLY here.

Captured against the real portal 2026-06-10. The eInvoice app is JSF/Mojarra:
dropdown changes fire AJAX partial re-renders (no navigation), so never cache
element handles — re-query every time.
"""

# ---------------------------------------------------------------- Okta login
# In Okta Identity Engine the password input AND the email-verification code
# input share name="credentials.passcode" — they differ only by type=
# (password vs text). Keep the [type=...] qualifiers.
OKTA_USERNAME = 'input[name="identifier"], input#okta-signin-username'
OKTA_PASSWORD = 'input[name="credentials.passcode"][type="password"], input#okta-signin-password'
OKTA_SUBMIT = 'input[type="submit"], button[type="submit"]'
OKTA_ERROR = '.o-form-error-container:not(:empty), .okta-form-infobox-error, [role="alert"]'

OKTA_CHOOSER_PASSWORD = 'div[data-se="okta_password"] a[data-se="button"]'
OKTA_CHOOSER_EMAIL = 'div[data-se="okta_email"] a[data-se="button"]'

OKTA_SEND_EMAIL_BTN = ('button:has-text("Send me an email"), '
                       'input[value="Send me an email"], a:has-text("Send me an email")')
OKTA_ENTER_CODE_CANDIDATES = [
    'a[data-se="enter-auth-code-instead-link"]',
    'a:has-text("Enter a verification code instead"), a:has-text("Enter a code from the email instead")',
    'button:has-text("Enter a verification code instead")',
    'text=/enter (a )?(verification )?code/i',
]
OKTA_CODE_INPUT = ('input[name="credentials.passcode"][type="text"], '
                   'input[name="answer"], input[autocomplete="one-time-code"]')
OKTA_VERIFY_BTN = ('input[type="submit"][value="Verify"], button:has-text("Verify"), '
                   'input[type="submit"]')

# ------------------------------------------------------------ Okta dashboard
DASHBOARD_MARKER = 'text="My Apps"'
EINVOICE_TILE = 'a:has-text("eInvoice"), [aria-label*="eInvoice"], a:has-text("eInvoicing")'

# ------------------------------------------------------------- eInvoice app
INVOICES_TAB = 'a:has-text("Invoices")'
SEARCH_SUBNAV = 'a:has-text("Search")'

BUSINESS_LINE_SELECT = 'select[id="mainForm:srchBusinessLine"]'
YEAR_QTR_INPUT = 'input[id="mainForm:srchYearQtr"]'
INVOICE_NUMBER_INPUT = 'input[id="mainForm:invoiceNumber"]'
PROGRAM_SELECT = 'select[id="mainForm:srchProgramName"]'
LABELER_SELECT = 'select[id="mainForm:labelerCode"]'

SEARCH_BUTTON = 'input[id="mainForm:go"]'
CLEAR_BUTTON = 'a:has-text("Clear"), input[value="Clear" i]'

NO_RECORDS = 'text=/no (records|results|data|invoices)/i'
RESULTS_TABLE = 'table[id="mainForm:labelerTable"]'
RESULTS_ROW = 'table[id="mainForm:labelerTable"] tbody tr'
ROW_CHECKBOX = 'input[title="selectionCheckbox"]'
TOTAL_RECORDS = 'span[id="mainForm:totalCount"]'

JUMP_PAGE_SELECT = 'select[id="mainForm:invoicePageScroller"]'

REPORT_TYPE_SELECT = 'select[id="mainForm:selectedFormatType"]'
REPORT_TYPE_VALUES = {
    "View Combined Invoice in PDF Format": "Combined",
    "Export in CMS Format": "cmsFormat",
}
CONTINUE_BUTTON = 'input[id="mainForm:continueButton"]'

# After selecting a single invoice and clicking Continue, the portal stages the
# report and shows an acknowledgment screen with a SECOND Continue; the file is
# not released until it's clicked. The marker is the acknowledgment notice; the
# button can carry the same id or a generic "Continue" value, so match either
# and require it to be visible (the staged results page can still be behind it).
ACK_RECEIPT_MARKER = 'text=/acknowledging receipt of invoice data/i'
ACK_CONTINUE = ('input[id="mainForm:continueButton"]:visible, '
                'input[type="submit"][value="Continue" i]:visible, '
                'input[type="button"][value="Continue" i]:visible, '
                'button:has-text("Continue"):visible')

ROW_DOWNLOAD_BTN = 'input[value*="Download" i]:not([disabled]), a:has-text("DOWNLOAD")'
ROW_NO_DATA = 'input[value="No Invoice Data" i]'

SESSION_EXPIRED_MARKERS = [OKTA_USERNAME, 'text=/session.{0,20}(expired|timed out)/i']

# Any of these appearing mid-run means the portal bounced us back to Okta and we
# must re-authenticate (a full sign-in form, or a step-up MFA challenge). All are
# Okta-specific, so they won't false-positive on the eInvoice pages.
REAUTH_MARKERS = [OKTA_USERNAME, OKTA_CODE_INPUT, OKTA_SEND_EMAIL_BTN,
                  'text=/session.{0,20}(expired|timed out)/i']
