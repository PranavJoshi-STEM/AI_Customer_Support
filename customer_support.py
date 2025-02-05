import imaplib
import smtplib
import email
import time
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from creds import EMAIL, PASSWORD, OPENAI_API_KEY  # Make sure this file exists with your credentials
import openai

openai.api_key = OPENAI_API_KEY

IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

def generate_gpt_response(email_thread):
    """Generate an AI response with thread awareness."""
    messages = [{"role": "system", "content": "You are a helpful customer support AI."}]
    for msg in email_thread:
        messages.append({"role": "user", "content": msg})
    
    response = openai.ChatCompletion.create(
        model="gpt-4",  # Or another suitable model
        messages=messages
    )
    reply_text = response.choices[0].message.content if response.choices else "Sorry, an error occurred while generating a response."  # Simplified access
    footer = "\n\nThis AI assistant is experimental; nothing in this conversation is legally binding. The AI is aware of previous emails in this thread."
    return reply_text + footer

def check_inbox():
    mail = imaplib.IMAP4_SSL(IMAP_SERVER)
    mail.login(EMAIL, PASSWORD)
    mail.select("inbox")
    _, messages = mail.search(None, "UNSEEN")
    mail.close()  # Important to close the connection
    mail.logout()
    return messages[0].split() if messages[0] else []

def fetch_email(mail, email_id):
    _, msg_data = mail.fetch(email_id, "(RFC822)")
    msg = email.message_from_bytes(msg_data[0][1]) if msg_data and msg_data[0] else None
    if not msg:
        return None, None, None, None, None

    sender = msg.get("From", "Unknown Sender")
    subject = msg.get("Subject", "No Subject")
    in_reply_to = msg.get("In-Reply-To")
    references = msg.get("References")

    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain": #  and part.get_content_disposition() == "inline":  Removed inline check, often not present
                body = part.get_payload(decode=True).decode(errors="ignore")
                break  # Stop after finding the first text/plain part
    elif msg.get_content_type() == "text/plain":  # Handle non-multipart emails
        body = msg.get_payload(decode=True).decode(errors="ignore")
    else:
        body = "(No plain text message body found)"  # Indicate if no plain text

    return sender, subject, body, in_reply_to, references


def fetch_email_thread(mail, references):
    thread_messages = []
    if references:
        ref_ids = references.split()
        for ref_id in ref_ids:  # Fetch all referenced messages
            try:
                _, msg_data = mail.fetch(ref_id, "(RFC822)")
                if msg_data and msg_data[0]:
                    msg = email.message_from_bytes(msg_data[0][1])
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors="ignore")
                                break
                    elif msg.get_content_type() == "text/plain":
                        body = msg.get_payload(decode=True).decode(errors="ignore")
                    if body:  # Only add if a body was found
                        thread_messages.append(body)

            except Exception as e:
                print(f"Error fetching referenced email: {e}")  # Print specific errors
                continue
    return thread_messages


def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as server: # Use SMTP_SSL for secure connection
        server.login(EMAIL, PASSWORD)
        server.sendmail(EMAIL, to_email, msg.as_string())
    print("Email sent successfully.")


def process_emails():
    while True:
        email_ids = check_inbox()
        print(f"Found {len(email_ids)} new emails.")

        mail = imaplib.IMAP4_SSL(IMAP_SERVER) # Move inside the loop
        mail.login(EMAIL, PASSWORD)
        mail.select("inbox")

        for email_id in email_ids:
            sender, subject, body, in_reply_to, references = fetch_email(mail, email_id)
            if not sender or not body:
                print("Skipping email with missing sender or body.")
                continue

            email_thread = [body] + fetch_email_thread(mail, references)
            
            ai_response = generate_gpt_response(email_thread)
            send_email(sender, f"Re: {subject}", ai_response)

            mail.store(email_id, '+FLAGS', '\\Seen') # Mark the email as read to prevent reprocessing.

        mail.close()
        mail.logout()
        print("Sleeping for 15 seconds before checking again...")
        time.sleep(15)

if __name__ == "__main__":
    process_emails()