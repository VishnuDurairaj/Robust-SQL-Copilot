import smtplib
import markdown
from email import encoders
from pydantic import EmailStr
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from typing import List, Optional, Dict, Any
from email.mime.multipart import MIMEMultipart

class SendMail:
    """
    A model to send emails with optional attachments.
    """
    def __init__(self, sender_email: str, sender_password: str, smtp_server: str, smtp_port: int) -> None:
        self.sender_email = sender_email
        self.sender_password = sender_password
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port

    def send_mail(self, recipients: List[EmailStr], subject: str, body: str, mail_cc: Optional[List[EmailStr]] = None, attachment: Optional[str] = None, attachment_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Send the email using the SMTP server details.
        """
        try:
            # Prepare the email message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = ",".join(recipients)
            if mail_cc:
                msg['CC'] = ",".join(mail_cc)
            msg.preamble = 'Multipart message.\n'

            # Convert Markdown body to HTML and attach it
            if body:
                html_body = markdown.markdown(body)
                part_body = MIMEText(html_body, 'html')
                msg.attach(part_body)

            # Attach the file if provided
            if attachment:
                try:
                    part = MIMEBase('application', "octet-stream")
                    with open(attachment, "rb") as file:
                        part.set_payload(file.read())
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f'attachment; filename={attachment_name or attachment}')
                    msg.attach(part)
                except Exception as err:
                    return {"status": "error", "message": f"Error attaching file: {err}"}

            # Send the email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, recipients + (mail_cc or []), msg.as_string())

            return {"status": "success", "message": "Email Sent"}

        except Exception as err:
            return {"status": "error", "message": f"Error while sending mail: {err}: Enabling the `Less secure app access` option in your Gmail account settings may help resolve this issue."}



import os
import base64
import markdown
from email.message import EmailMessage
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

class GmailHandler:
    def __init__(self, 
                 token_path="token.json", 
                 creds_path="credentials.json", 
                 sender_email="default_sender@example.com"):
        """
        Initialize the GmailHandler.
        
        :param token_path: Path to the token file for saved credentials.
        :param creds_path: Path to the credentials file from Google Cloud.
        :param sender_email: Default sender email address.
        """
        self.token_path = token_path
        self.creds_path = creds_path
        self.sender_email = sender_email
        self.creds = None
        self._authenticate()

    def _authenticate(self):
        """Handle Google authentication and create credentials."""
        if os.path.exists(self.token_path):
            self.creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
        
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.creds_path, SCOPES)
                self.creds = flow.run_local_server(port=0)
            
            # Save credentials for future use
            with open(self.token_path, "w") as token:
                token.write(self.creds.to_json())

    def send_mail(self, to_email, subject, body_md, cc_email=None, attachment_paths=None):
        """
        Send an email via Gmail API.
        
        :param to_email: Recipient email address.
        :param subject: Subject of the email.
        :param body_md: Email body in Markdown format.
        :param cc_email: List of CC email addresses (optional).
        :param attachment_paths: List of file paths to attach (optional).
        :return: Sent email metadata.
        """
        try:
            service = build("gmail", "v1", credentials=self.creds)

            # Convert Markdown to HTML
            body_html = markdown.markdown(body_md)

            # Create the email message
            message = EmailMessage()
            message.set_content(body_md, subtype='plain')  # Plain text version
            message.add_alternative(body_html, subtype='html')  # HTML version

            message["To"] = to_email
            message["From"] = self.sender_email
            message["Subject"] = subject

            # Add CC if provided
            if cc_email:
                if isinstance(cc_email, list):
                    message["Cc"] = ", ".join(cc_email)
                else:
                    message["Cc"] = cc_email

            # Handle attachments if provided
            if attachment_paths:
                for attachment_path in attachment_paths:
                    with open(attachment_path, "rb") as f:
                        file_data = f.read()
                        file_name = os.path.basename(attachment_path)
                        message.add_attachment(file_data, maintype="application", subtype="octet-stream", filename=file_name)

            # Encode the message
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            send_message = {"raw": encoded_message}

            # Send the email
            sent_message = service.users().messages().send(userId="me", body=send_message).execute()
            print(f"Email sent successfully with id: {sent_message['id']}")
            return sent_message

        except HttpError as error:
            print(f"An error occurred while sending email: {error}")
            return f"An error occurred while sending email: {error}"
