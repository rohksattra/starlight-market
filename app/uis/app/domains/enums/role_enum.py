# app/domains/enums/role_enum.py
from enum import Enum
from typing import Literal


class ServerRole(str, Enum):
    BOT_DEVELOPER = "bot_developer"
    BANK_MANAGER = "bank_manager"
    MODERATOR = "moderator"
    WORKER = "worker"
    CUSTOMER = "customer"


STAFF_ROLE = {
    ServerRole.BOT_DEVELOPER,
    ServerRole.BANK_MANAGER,
    ServerRole.MODERATOR,
}

ORDER_MANAGEMENT_ROLES = {
    ServerRole.BOT_DEVELOPER,
    ServerRole.BANK_MANAGER,
}

USER_ROLE = Literal [
    ServerRole.WORKER,
    ServerRole.CUSTOMER,
]