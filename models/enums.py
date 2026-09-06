from enum import StrEnum


class OrderStatus(StrEnum):
    NEW = "new"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    CLOSED = "closed"
    CANCELED = "canceled"


class ServerRole(StrEnum):
    BOT_DEVELOPER = "bot_developer"
    BANK_MANAGER = "bank_manager"
    MODERATOR = "moderator"
    WORKER = "worker"
    CUSTOMER = "customer"


ORDER_MANAGEMENT_ROLES: frozenset[ServerRole] = frozenset({
    ServerRole.BOT_DEVELOPER,
    ServerRole.BANK_MANAGER,
})

STAFF_ROLES: frozenset[ServerRole] = frozenset({
    ServerRole.BOT_DEVELOPER,
    ServerRole.BANK_MANAGER,
    ServerRole.MODERATOR,
})
