
import logging, os, sys, smtplib
from ssl import SSLError
from collections import OrderedDict

from ..command import Cmd
from ..item import ItemList

logger = logging.getLogger(__name__)

class Plugin(Cmd):

    name = 'email'
    desc = 'Notify with status message via email'
    stage = 'filter'
    filter_on_output = ['clean']
    inputs_from = ['clean','setup']
    MAX_MSGS_PER_SENDER = 3
    
    options = ['--email-smtp_login=USERNAME      Username for email server',
               '--email-smtp_password=PASSWORD   Password for email server',
               '--email-smtp_dest=TARGET_EMAIL   Where to send notificdation email',
    ]

    def _find_executable(self):
        return

    async def run(self, item_list, original_pdf_list):
        """Only send in up to 3 pages data
        """
        msg_dict = OrderedDict()  # Keys are the stage names
        msgs = await self.get_messages()
        for sender, msg in msgs:
            sender_msg_list = msg_dict.get(sender, [])
            sender_msg_list.append(msg)
            msg_dict[sender] = sender_msg_list

        msg_list = []
        for sender, msgs in msg_dict.items():
            if len(msgs) > self.MAX_MSGS_PER_SENDER:
                msg_list.append(f'{sender}: {msgs[0]}... {msgs[-1]}')
            else:
                for msg in msgs:
                    msg_list.append(f'{sender}: {msg}')

        msg = 'lexic processed\n' + '\n'.join(msg_list)

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