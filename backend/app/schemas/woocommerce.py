from pydantic import BaseModel


class WCImage(BaseModel):
    id: int = 0
    src: str = ""
    alt: str = ""


class WCCategory(BaseModel):
    id: int = 0
    name: str = ""
    slug: str = ""


class WCProduct(BaseModel):
    id: int
    name: str
    slug: str
    price: str = ""
    stock_status: str = ""
    permalink: str = ""
    images: list[WCImage] = []
    categories: list[WCCategory] = []


class WCBilling(BaseModel):
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""


class WCLineItem(BaseModel):
    id: int = 0
    name: str = ""
    quantity: int = 0
    total: str = ""
    product_id: int = 0


class WCOrder(BaseModel):
    id: int
    status: str
    total: str = ""
    currency: str = ""
    customer_id: int = 0
    billing: WCBilling = WCBilling()
    line_items: list[WCLineItem] = []
    date_created: str = ""
