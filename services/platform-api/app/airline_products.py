"""Curated public service categories with explicit fictional commercial terms."""
from sqlalchemy import select
from .db_models import ProductPackageRecord
from .ontology.projection import put_entity, put_relation

# Category references only; no price/inventory is represented as official.
REFERENCE_URL = "https://www.ceair.com/zh/cny/home"
PUBLIC_CATEGORY_CODES = {"BAG", "SEAT", "WIFI", "LOUNGE", "UPGRADE", "MILES", "RAIL", "MEAL", "CHILD", "INSURANCE"}
PRODUCTS = [
    ('BAG', '预付额外行李', '行李服务', '额外托运行李额度', '按航线计重或计件；婴儿票、特殊行李单独核验', 199),
    ('SEAT', '优选座位', '座位服务', '前排或指定区域座位', '机型与航班座位状态待核验；紧急出口需符合资格', 89),
    ('WIFI', '机上互联', '机上服务', '全航程网络服务', '仅支持互联的执飞航班；设备与服务时段受限', 58),
    ('LOUNGE', '机场贵宾休息室', '机场服务', '出发前休息室服务', '指定机场及营业时段；是否含同行人以规则为准', 168),
    ('UPGRADE', '付费升舱', '客舱体验', '更高舱等体验', '原客票与航班可升舱库存；退改规则独立核验', 699),
    ('MILES', '会员里程加赠', '会员权益', '航段额外里程权益', '会员身份、票价适用及飞行完成条件', 0),
    ('RAIL', '空铁联运', '联运产品', '航空与铁路行程衔接', '指定合作城市与车次；衔接时间需核验', 99),
    ('EARLY', '提前购票优惠', '客票产品', '提前规划的优惠运价', '指定提前购票天数、航班与销售有效期', 599),
    ('FLEX', '灵活退改票价', '客票产品', '灵活行程服务', '退改手续费、次数及差价按票价条款', 899),
    ('FAMILY', '家庭邻座服务', '座位服务', '家庭同行座位安排', '同一订单及同行证据；受剩余连座资源限制', 129),
    ('MEAL', '特色餐食预订', '机上服务', '航程餐食预订', '指定机型、航线及提前预订窗口；特殊餐需另行确认', 49),
    ('PICKUP', '目的地接送', '出行服务', '指定城市机场接送', '目的机场、服务半径、车次和预约时间核验', 139),
    ('PET', '宠物托运服务', '行李服务', '符合条件的小动物运输', '航班机型、检疫文件、容器及舱位数量需人工审核', 299),
    ('CHILD', '无陪儿童服务', '特殊服务', '儿童出行陪护', '年龄、国内/国际航线、监护手续及服务容量核验', 200),
    ('YOUTH', '青年出行优惠', '客票产品', '符合年龄的指定运价', '出生日期资格、证件及票价有效期核验', 499),
    ('SENIOR', '长者关怀服务', '特殊服务', '协助与服务预约', '需本人授权；辅助服务预约不构成医疗承诺', 0),
    ('TRANSFER', '中转住宿权益', '中转服务', '符合时长的住宿安排', '联程客票、中转机场、时长与签证资格核验', 0),
    ('HOTEL', '机酒出行组合', '出行服务', '机票与合作酒店权益', '酒店日期、入住人数、房型与退改各自核验', 1299),
    ('C919', '国产大飞机体验', '客舱体验', '指定机型航班体验', '以实际执飞机型为准，换机后权益复核', 99),
    ('LOWCARBON', '绿色出行权益', '绿色出行', '低碳出行主题权益', '指定活动范围；不对碳减排量作未经验证的承诺', 0),
    ('BUSINESS', '企业差旅服务包', '企业产品', '灵活行程与企业服务', '企业合同、员工授权与结算资格核验', 999),
    ('FREQUENT', '多次往返权益', '客票产品', '固定航线多次出行组合', '指定航线、乘机次数、兑换窗口及实名限制', 1999),
    ('INSURANCE', '旅行保障合作产品', '出行服务', '出行保险服务入口', '由持牌机构提供；条款和投保资格需独立确认', 30),
    ('PRIORITY', '机场优先服务', '机场服务', '指定优先值机服务', '机场、会员等级或付费资格，安检以机场规则为准', 99),]


def catalog_products():
    return [{"code": "M-DEMO-"+code, "name": name, "category": category,
        "benefits": [benefit], "eligibility": eligibility, "status": "待上游核验",
        "price_yuan": price, "price_mode": "演示参考价", "inventory": None,
        "data_mode": "公开服务分类参考与模拟条款", "source": "公开航空服务目录与项目产品设计",
        "reference_url": REFERENCE_URL if code in PUBLIC_CATEGORY_CODES else None,
        "reference_checked_at": "2026-10-13" if code in PUBLIC_CATEGORY_CODES else None,
        "category_basis": "公开服务分类参考" if code in PUBLIC_CATEGORY_CODES else "项目设计扩展",
        "valid_from": "2026-10-01", "valid_to": "2027-09-30", "channels": ["App","官网"],
        "route_scope": "指定适用航线，需上游核验", "cabin_scope": "按产品规则核验",
        "member_scope": "按产品规则核验", "synthetic": True}
        for code,name,category,benefit,eligibility,price in PRODUCTS]


def seed_airline_products(session, tenant_id, user_id):
    for item in catalog_products():
        package = session.scalar(select(ProductPackageRecord).where(
            ProductPackageRecord.tenant_id == tenant_id, ProductPackageRecord.external_id == item["code"]))
        if package is None:
            session.add(ProductPackageRecord(tenant_id=tenant_id, external_id=item["code"],
                name=item["name"], product_type=item["category"], description=item["benefits"][0]+"；模拟产品，价格库存待核验",
                eligibility=item["eligibility"], status="草稿", created_by=user_id))
        pn = put_entity(session, tenant_id, item["code"], "ProductPackage", item["name"], item, "公开分类参考与模拟条款")
        product = put_entity(session, tenant_id, item["code"]+"-PRODUCT", "Product", item["name"], item, "公开分类参考与模拟条款")
        put_relation(session, tenant_id, pn, "contains_product", product, "模拟产品结构")
    session.commit()
