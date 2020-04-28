
import logging, os, sys, smtplib
from ssl import SSLError

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

class Plugin(Cmd):

    name = 'email'
    desc = 'Notify with status message via email'
    stage = 'filter'
    filter_on_output = ['clean']
    inputs_from = ['clean','setup']
    
    options = ['--email-smtp_login=USERNAME      Username for email server',
               '--email-smtp_password=PASSWORD   Password for email server',
               '--email-smtp_dest=TARGET_EMAIL   Where to send notificdation email',
    ]

    def _find_executable(self):
        return

    async def run(self, item_list, original_pdf_list):

        msgs = await self.get_messages()
        msg = 'lexic processed\n' + '\n'.join(msgs)

        logger.info('sending status to email')
        logger.debug(msg)
        try:
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.config['smtp_login'], self.config['smtp_password'])
            server.sendmail(self.config['smtp_login'], self.config['smtp_dest'], msg)
            server.quit()
        except SSLError as e:
            print("ERROR SENDING EMAIL")

        return item_list