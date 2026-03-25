# app/domains/enums/order_status_enum.py
from enum import StrEnum

class OrderStatus(StrEnum):
    NEW = "new"
    CLAIMED = "claimed"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    CLOSED = "closed"
    CANCELED = "canceled"
