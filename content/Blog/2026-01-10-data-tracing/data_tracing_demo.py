"""
数据溯源系统实现示例
=====================

业务关系：
- Order → Payment (1:1)
- Payment → EnterpriseTotalAmount (N:1, 按企业汇总)
- EnterpriseTotalAmount → TotalAmount (N:1, 汇总总账)

需求：
0. Payment会和Order进行匹配
1. 记录企业账来自哪几个Payment
2. 记录总账单来自哪个企业账、哪个Payment
3. 从Payment查询，可以跟踪来源的多个订单以及后续的1个企业账单和1个总账单
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Set
from datetime import datetime
import uuid


@dataclass
class Order:
    """订单实体 - 纯数据，不包含关系"""
    id: str
    amount: float
    enterprise_id: str
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Payment:
    """支付实体 - 纯数据，不包含关系"""
    id: str
    enterprise_id: str    # 所属企业ID
    amount: float
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class EnterpriseTotalAmount:
    """企业账单实体 - 纯数据，不包含关系"""
    id: str
    enterprise_id: str
    total_amount: float
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class TotalAmount:
    """总账单实体 - 纯数据，不包含关系"""
    id: str
    total_amount: float
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class RelationshipMapping:
    """独立的关系映射数据结构"""

    # Payment -> Orders (N:1)
    payment_to_orders: Dict[str, Set[str]] = field(default_factory=dict)

    # Payment -> EnterpriseTotal (N:1)
    payment_to_enterprise_total: Dict[str, str] = field(default_factory=dict)

    # EnterpriseTotal -> Payments (1:N)
    enterprise_total_to_payments: Dict[str, Set[str]] = field(default_factory=dict)

    # EnterpriseTotal -> TotalAmount (N:1)
    enterprise_total_to_total: Dict[str, str] = field(default_factory=dict)

    # TotalAmount -> EnterpriseTotals (1:N)
    total_to_enterprise_totals: Dict[str, Set[str]] = field(default_factory=dict)

    def add_payment_order(self, payment_id: str, order_id: str):
        """添加Payment-Order关系"""
        if payment_id not in self.payment_to_orders:
            self.payment_to_orders[payment_id] = set()
        self.payment_to_orders[payment_id].add(order_id)

    def add_payment_enterprise_total(self, payment_id: str, enterprise_total_id: str):
        """添加Payment-EnterpriseTotal关系"""
        self.payment_to_enterprise_total[payment_id] = enterprise_total_id

        if enterprise_total_id not in self.enterprise_total_to_payments:
            self.enterprise_total_to_payments[enterprise_total_id] = set()
        self.enterprise_total_to_payments[enterprise_total_id].add(payment_id)

    def add_enterprise_total_total(self, enterprise_total_id: str, total_amount_id: str):
        """添加EnterpriseTotal-TotalAmount关系"""
        self.enterprise_total_to_total[enterprise_total_id] = total_amount_id

        if total_amount_id not in self.total_to_enterprise_totals:
            self.total_to_enterprise_totals[total_amount_id] = set()
        self.total_to_enterprise_totals[total_amount_id].add(enterprise_total_id)

    def get_orders_by_payment(self, payment_id: str) -> Set[str]:
        """获取Payment关联的所有订单"""
        return self.payment_to_orders.get(payment_id, set())

    def get_enterprise_total_by_payment(self, payment_id: str) -> Optional[str]:
        """获取Payment所属的企业账单"""
        return self.payment_to_enterprise_total.get(payment_id)

    def get_total_by_enterprise_total(self, enterprise_total_id: str) -> Optional[str]:
        """获取EnterpriseTotal所属的总账单"""
        return self.enterprise_total_to_total.get(enterprise_total_id)

    def get_payments_by_enterprise_total(self, enterprise_total_id: str) -> Set[str]:
        """获取EnterpriseTotal关联的所有Payment"""
        return self.enterprise_total_to_payments.get(enterprise_total_id, set())

    def get_enterprise_totals_by_total(self, total_id: str) -> Set[str]:
        """获取Total关联的所有EnterpriseTotal"""
        return self.total_to_enterprise_totals.get(total_id, set())

    # ========== 状态查询方法 ==========

    def get_payments_without_enterprise_total(self, all_payment_ids: Set[str] = None) -> Set[str]:
        """获取所有未生成企业账单的Payment ID

        Args:
            all_payment_ids: 所有已创建的Payment ID集合，如果不提供则使用payment_to_enterprise_total的键

        Returns:
            没有企业账单的Payment ID集合
        """
        # 如果没有提供所有Payment ID，则使用payment_to_enterprise_total的键
        if all_payment_ids is None:
            all_payments = set(self.payment_to_enterprise_total.keys())
        else:
            all_payments = all_payment_ids

        # 找出已经有企业账单的Payment
        payments_with_enterprise = set()
        for payment_id in all_payments:
            if payment_id in self.payment_to_enterprise_total:
                ent_id = self.payment_to_enterprise_total[payment_id]
                if ent_id:  # 确保企业账单ID不为空
                    payments_with_enterprise.add(payment_id)

        # 返回没有企业账单的Payment
        return all_payments - payments_with_enterprise

    def get_enterprise_totals_without_total(self) -> Set[str]:
        """获取所有未生成总账单的EnterpriseTotal ID"""
        # 所有EnterpriseTotal减去已有总账单关联的EnterpriseTotal
        all_enterprise_totals = set(self.enterprise_total_to_total.keys())

        # 找出没有总账单的EnterpriseTotal
        enterprise_totals_with_total = set()
        for ent_id in all_enterprise_totals:
            if self.enterprise_total_to_total[ent_id]:
                enterprise_totals_with_total.add(ent_id)

        return all_enterprise_totals - enterprise_totals_with_total

    def get_incomplete_payments(self, all_payment_ids: Set[str] = None) -> Dict[str, Set[str]]:
        """获取所有不完整的Payment（缺少企业账单或总账单）

        Args:
            all_payment_ids: 所有已创建的Payment ID集合，如果不提供则使用payment_to_enterprise_total的键

        Returns:
            包含不完整Payment信息的字典
        """
        result = {
            "missing_enterprise_total": set(),
            "missing_total": set(),
            "completely_missing": set()  # 既缺企业账单又缺总账单
        }

        # 获取所有需要检查的Payment ID
        if all_payment_ids is None:
            all_payments = set(self.payment_to_enterprise_total.keys())
        else:
            all_payments = all_payment_ids

        # 检查每个Payment
        for payment_id in all_payments:
            ent_id = self.payment_to_enterprise_total.get(payment_id)

            if not ent_id:
                # 缺少企业账单
                result["missing_enterprise_total"].add(payment_id)
                result["completely_missing"].add(payment_id)
            else:
                # 检查企业账单是否有总账单
                total_id = self.enterprise_total_to_total.get(ent_id)
                if not total_id:
                    result["missing_total"].add(payment_id)

        return result

    def get_completeness_summary(self) -> Dict:
        """获取数据完整性统计"""
        total_payments = len(self.payment_to_orders)
        total_enterprise_totals = len(self.enterprise_total_to_payments)
        total_amounts = len(self.total_to_enterprise_totals)

        # 计算完整性
        payments_with_enterprise = len(self.payment_to_enterprise_total)
        enterprise_totals_with_total = len(self.enterprise_total_to_total)

        return {
            "total_payments": total_payments,
            "payments_with_enterprise": payments_with_enterprise,
            "payments_without_enterprise": total_payments - payments_with_enterprise,
            "total_enterprise_totals": total_enterprise_totals,
            "enterprise_totals_with_total": enterprise_totals_with_total,
            "enterprise_totals_without_total": total_enterprise_totals - enterprise_totals_with_total,
            "total_amounts": total_amounts,
            "completeness_rate": {
                "payment_to_enterprise": f"{(payments_with_enterprise/total_payments*100):.1f}%" if total_payments > 0 else "0%",
                "enterprise_to_total": f"{(enterprise_totals_with_total/total_enterprise_totals*100):.1f}%" if total_enterprise_totals > 0 else "0%"
            }
        }


class DataTracingSystem:
    """数据溯源系统 - 使用独立的关系映射"""

    def __init__(self):
        # 纯数据存储
        self.orders: Dict[str, Order] = {}
        self.payments: Dict[str, Payment] = {}
        self.enterprise_totals: Dict[str, EnterpriseTotalAmount] = {}
        self.total_amounts: Dict[str, TotalAmount] = {}

        # 独立的关系映射
        self.relationships = RelationshipMapping()

    # ========== 创建数据 ==========

    def create_order(self, amount: float, enterprise_id: str) -> Order:
        """创建订单"""
        order = Order(
            id=f"ORD-{uuid.uuid4().hex[:8]}",
            amount=amount,
            enterprise_id=enterprise_id
        )
        self.orders[order.id] = order
        return order

    def create_payment(self, order_ids: List[str], enterprise_id: str) -> Payment:
        """创建支付并匹配订单"""
        # 验证订单存在且属于同一企业
        total_amount = 0
        for order_id in order_ids:
            if order_id not in self.orders:
                raise ValueError(f"订单 {order_id} 不存在")
            if self.orders[order_id].enterprise_id != enterprise_id:
                raise ValueError(f"订单 {order_id} 不属于企业 {enterprise_id}")
            total_amount += self.orders[order_id].amount

        payment = Payment(
            id=f"PAY-{uuid.uuid4().hex[:8]}",
            enterprise_id=enterprise_id,
            amount=total_amount
        )
        self.payments[payment.id] = payment

        # 在独立的关系映射中记录关系
        for order_id in order_ids:
            self.relationships.add_payment_order(payment.id, order_id)

        return payment

    def create_enterprise_total(self, payment_ids: List[str]) -> EnterpriseTotalAmount:
        """创建企业账单"""
        if not payment_ids:
            raise ValueError("至少需要一个Payment")

        # 获取企业ID（从第一个Payment获取）
        enterprise_id = self.payments[payment_ids[0]].enterprise_id
        total_amount = 0

        for payment_id in payment_ids:
            if payment_id not in self.payments:
                raise ValueError(f"Payment {payment_id} 不存在")
            if self.payments[payment_id].enterprise_id != enterprise_id:
                raise ValueError(f"Payment {payment_id} 不属于同一企业")
            total_amount += self.payments[payment_id].amount

        enterprise_total = EnterpriseTotalAmount(
            id=f"ENT-{uuid.uuid4().hex[:8]}",
            enterprise_id=enterprise_id,
            total_amount=total_amount
        )

        # 在独立的关系映射中记录关系
        for payment_id in payment_ids:
            self.relationships.add_payment_enterprise_total(payment_id, enterprise_total.id)

        self.enterprise_totals[enterprise_total.id] = enterprise_total
        return enterprise_total

    def create_total_amount(self, enterprise_total_ids: List[str]) -> TotalAmount:
        """创建总账单"""
        if not enterprise_total_ids:
            raise ValueError("至少需要一个企业账单")

        total_amount = 0
        for ent_id in enterprise_total_ids:
            if ent_id not in self.enterprise_totals:
                raise ValueError(f"企业账单 {ent_id} 不存在")
            total_amount += self.enterprise_totals[ent_id].total_amount

        total = TotalAmount(
            id=f"TOT-{uuid.uuid4().hex[:8]}",
            total_amount=total_amount
        )

        # 在独立的关系映射中记录关系
        for ent_id in enterprise_total_ids:
            self.relationships.add_enterprise_total_total(ent_id, total.id)

        self.total_amounts[total.id] = total
        return total

    # ========== 溯源查询 ==========

    def trace_payment_forward(self, payment_id: str) -> Dict:
        """正向溯源：Payment → Orders → Enterprise → Total"""
        if payment_id not in self.payments:
            raise ValueError(f"Payment {payment_id} 不存在")

        payment = self.payments[payment_id]

        # 从独立的关系映射中获取关联数据
        order_ids = self.relationships.get_orders_by_payment(payment_id)
        orders = [self.orders[oid] for oid in order_ids]

        # 获取企业账单
        enterprise_total = None
        enterprise_total_id = self.relationships.get_enterprise_total_by_payment(payment_id)
        if enterprise_total_id:
            enterprise_total = self.enterprise_totals[enterprise_total_id]

        # 获取总账单
        total_amount = None
        if enterprise_total_id:
            total_amount_id = self.relationships.get_total_by_enterprise_total(enterprise_total_id)
            if total_amount_id:
                total_amount = self.total_amounts[total_amount_id]

        return {
            "payment": payment,
            "orders": orders,
            "enterprise_total": enterprise_total,
            "total_amount": total_amount
        }

    def trace_total_backward(self, total_id: str) -> Dict:
        """反向溯源：Total → Enterprise → Payments → Orders"""
        if total_id not in self.total_amounts:
            raise ValueError(f"TotalAmount {total_id} 不存在")

        total = self.total_amounts[total_id]

        # 从独立的关系映射中获取关联数据
        enterprise_total_ids = self.relationships.get_enterprise_totals_by_total(total_id)
        enterprise_totals = [self.enterprise_totals[ent_id] for ent_id in enterprise_total_ids]

        # 获取所有Payment
        all_payments = []
        for ent_id in enterprise_total_ids:
            payment_ids = self.relationships.get_payments_by_enterprise_total(ent_id)
            all_payments.extend([self.payments[pid] for pid in payment_ids])

        # 获取所有订单
        all_orders = []
        for payment in all_payments:
            order_ids = self.relationships.get_orders_by_payment(payment.id)
            all_orders.extend([self.orders[oid] for oid in order_ids])

        return {
            "total_amount": total,
            "enterprise_totals": enterprise_totals,
            "payments": all_payments,
            "orders": all_orders
        }

    def trace_enterprise_backward(self, enterprise_total_id: str) -> Dict:
        """反向溯源：Enterprise → Payments → Orders"""
        if enterprise_total_id not in self.enterprise_totals:
            raise ValueError(f"EnterpriseTotalAmount {enterprise_total_id} 不存在")

        ent = self.enterprise_totals[enterprise_total_id]

        # 从独立的关系映射中获取关联数据
        payment_ids = self.relationships.get_payments_by_enterprise_total(enterprise_total_id)
        payments = [self.payments[pid] for pid in payment_ids]

        # 获取订单
        orders = []
        for payment in payments:
            order_ids = self.relationships.get_orders_by_payment(payment.id)
            orders.extend([self.orders[oid] for oid in order_ids])

        return {
            "enterprise_total": ent,
            "payments": payments,
            "orders": orders
        }

    # ========== 高级查询 ==========

    def get_payment_trace_summary(self, payment_id: str) -> str:
        """获取Payment的完整溯源摘要"""
        trace = self.trace_payment_forward(payment_id)

        payment = trace["payment"]
        orders = trace["orders"]
        enterprise_total = trace["enterprise_total"]
        total_amount = trace["total_amount"]

        summary = f"""
=== Payment {payment_id} 溯源摘要 ===
Payment信息:
  - ID: {payment.id}
  - 金额: {payment.amount}
  - 企业: {payment.enterprise_id}

关联订单 ({len(orders)}个):
"""
        for order in orders:
            summary += f"  - {order.id}: ¥{order.amount}\n"

        if enterprise_total:
            summary += f"""
企业账单:
  - ID: {enterprise_total.id}
  - 金额: {enterprise_total.total_amount}
"""
        else:
            summary += "企业账单: 未生成\n"

        if total_amount:
            summary += f"""
总账单:
  - ID: {total_amount.id}
  - 金额: {total_amount.total_amount}
"""
        else:
            summary += "总账单: 未生成\n"

        return summary

    def get_total_trace_summary(self, total_id: str) -> str:
        """获取TotalAmount的完整溯源摘要"""
        trace = self.trace_total_backward(total_id)

        total = trace["total_amount"]
        enterprise_totals = trace["enterprise_totals"]
        payments = trace["payments"]
        orders = trace["orders"]

        summary = f"""
=== TotalAmount {total_id} 溯源摘要 ===
总账单信息:
  - ID: {total.id}
  - 总金额: {total.total_amount}

企业账单 ({len(enterprise_totals)}个):
"""
        for ent in enterprise_totals:
            summary += f"  - {ent.id}: ¥{ent.total_amount} (企业: {ent.enterprise_id})\n"

        summary += f"""
Payment ({len(payments)}个):
"""
        for pay in payments:
            summary += f"  - {pay.id}: ¥{pay.amount}\n"

        summary += f"""
订单 ({len(orders)}个):
"""
        for order in orders:
            summary += f"  - {order.id}: ¥{order.amount}\n"

        return summary

    # ========== 关系映射查询 ==========

    def get_relationship_summary(self) -> str:
        """获取当前所有关系映射的摘要"""
        rel = self.relationships

        summary = "=== 独立关系映射状态 ===\n"
        summary += f"Payment → Orders: {len(rel.payment_to_orders)} 条记录\n"
        summary += f"Payment → EnterpriseTotal: {len(rel.payment_to_enterprise_total)} 条记录\n"
        summary += f"EnterpriseTotal → Payments: {len(rel.enterprise_total_to_payments)} 条记录\n"
        summary += f"EnterpriseTotal → Total: {len(rel.enterprise_total_to_total)} 条记录\n"
        summary += f"Total → EnterpriseTotals: {len(rel.total_to_enterprise_totals)} 条记录\n"

        return summary

    def get_all_payment_ids(self) -> Set[str]:
        """获取所有已创建的Payment ID"""
        return set(self.payments.keys())


# ========== 使用示例 ==========

def demo():
    """演示数据溯源功能"""
    print("=== 数据溯源系统演示 ===\n")

    # 初始化系统
    system = DataTracingSystem()

    # 1. 创建订单
    print("1. 创建订单...")
    orders = [
        system.create_order(100, "enterprise_A"),
        system.create_order(200, "enterprise_A"),
        system.create_order(150, "enterprise_B"),
        system.create_order(250, "enterprise_B"),
        system.create_order(300, "enterprise_A"),
    ]
    for order in orders:
        print(f"  创建订单 {order.id}: ¥{order.amount} (企业: {order.enterprise_id})")

    # 2. 创建Payment并匹配订单
    print("\n2. 创建Payment并匹配订单...")
    payments = [
        system.create_payment([orders[0].id, orders[1].id], "enterprise_A"),  # 企业A的Payment1
        system.create_payment([orders[2].id, orders[3].id], "enterprise_B"),  # 企业B的Payment
        system.create_payment([orders[4].id], "enterprise_A"),               # 企业A的Payment2
    ]
    for payment in payments:
        order_ids = system.relationships.get_orders_by_payment(payment.id)
        print(f"  创建Payment {payment.id}: ¥{payment.amount} (订单: {order_ids})")

    # 3. 创建企业账单
    print("\n3. 创建企业账单...")
    enterprise_totals = [
        system.create_enterprise_total([payments[0].id, payments[2].id]),  # 企业A的账单
        system.create_enterprise_total([payments[1].id]),                 # 企业B的账单
    ]
    for ent in enterprise_totals:
        payment_ids = system.relationships.get_payments_by_enterprise_total(ent.id)
        print(f"  创建企业账单 {ent.id}: ¥{ent.total_amount} (Payment: {payment_ids})")

    # 4. 创建总账单
    print("\n4. 创建总账单...")
    total = system.create_total_amount([ent.id for ent in enterprise_totals])
    print(f"  创建总账单 {total.id}: ¥{total.total_amount}")

    # 5. 溯源查询演示
    print("\n5. 溯源查询演示...")

    # 5.1 从Payment查询完整路径
    print("\n--- Payment正向溯源 ---")
    payment_1 = payments[0].id
    print(system.get_payment_trace_summary(payment_1))

    # 5.2 从Total反向查询
    print("\n--- Total反向溯源 ---")
    print(system.get_total_trace_summary(total.id))

    # 5.3 验证需求
    print("\n=== 需求验证 ===")

    # 需求0: Payment会和Order进行匹配 ✓
    print("✓ 需求0: Payment会和Order进行匹配")
    order_ids = system.relationships.get_orders_by_payment(payments[0].id)
    print(f"  Payment {payments[0].id} 关联订单: {order_ids}")

    # 需求1: 记录企业账来自哪几个Payment ✓
    print("\n✓ 需求1: 记录企业账来自哪几个Payment")
    payment_ids = system.relationships.get_payments_by_enterprise_total(enterprise_totals[0].id)
    print(f"  企业账单 {enterprise_totals[0].id} 来自Payment: {payment_ids}")

    # 需求2: 记录总账单来自哪个企业账、哪个Payment ✓
    print("\n✓ 需求2: 记录总账单来自哪个企业账、哪个Payment")
    ent_ids = system.relationships.get_enterprise_totals_by_total(total.id)
    print(f"  总账单 {total.id} 来自企业账: {ent_ids}")
    for ent_id in ent_ids:
        payment_ids = system.relationships.get_payments_by_enterprise_total(ent_id)
        print(f"    企业账 {ent_id} 来自Payment: {payment_ids}")

    # 需求3: 从Payment查询完整路径 ✓
    print("\n✓ 需求3: 从Payment查询完整路径")
    trace = system.trace_payment_forward(payments[0].id)
    print(f"  Payment {payments[0].id}")
    print(f"    → 订单: {[o.id for o in trace['orders']]}")
    print(f"    → 企业账: {trace['enterprise_total'].id if trace['enterprise_total'] else '未生成'}")
    print(f"    → 总账: {trace['total_amount'].id if trace['total_amount'] else '未生成'}")

    # 额外验证：展示独立关系映射
    print("\n=== 独立关系映射验证 ===")
    print(system.get_relationship_summary())

    # 展示数据分离的效果
    print("\n=== 数据分离效果展示 ===")
    print("Payment实体数据（无关系字段）:")
    print(f"  {payments[0]}")
    print("\n关系信息（独立存储）:")
    print(f"  Payment {payments[0].id} → 订单: {system.relationships.get_orders_by_payment(payments[0].id)}")
    ent_id = system.relationships.get_enterprise_total_by_payment(payments[0].id)
    if ent_id:
        print(f"  Payment {payments[0].id} → 企业账单: {ent_id}")
        total_id = system.relationships.get_total_by_enterprise_total(ent_id)
        if total_id:
            print(f"  企业账单 {ent_id} → 总账单: {total_id}")


def demo_incomplete_payments():
    """演示Payment无法匹配企业账、总账的情况"""
    print("\n=== Payment无法匹配案例演示 ===\n")

    # 初始化系统
    system = DataTracingSystem()

    # 1. 创建订单
    print("1. 创建订单...")
    orders = [
        system.create_order(100, "enterprise_A"),
        system.create_order(200, "enterprise_A"),
        system.create_order(150, "enterprise_B"),
        system.create_order(250, "enterprise_B"),
        system.create_order(300, "enterprise_A"),
        system.create_order(400, "enterprise_C"),  # 新企业C的订单
    ]
    for order in orders:
        print(f"  创建订单 {order.id}: ¥{order.amount} (企业: {order.enterprise_id})")

    # 2. 创建Payment - 故意制造不完整的数据
    print("\n2. 创建Payment（故意制造不匹配情况）...")

    # Payment 1: 完整路径（订单 → Payment → 企业账 → 总账）
    payment_complete = system.create_payment([orders[0].id, orders[1].id], "enterprise_A")
    print(f"  Payment {payment_complete.id}: ¥{payment_complete.amount} (订单: {[orders[0].id, orders[1].id]})")

    # Payment 2: 只有订单，没有企业账和总账（不完整）
    payment_no_enterprise = system.create_payment([orders[2].id, orders[3].id], "enterprise_B")
    print(f"  Payment {payment_no_enterprise.id}: ¥{payment_no_enterprise.amount} (订单: {[orders[2].id, orders[3].id]}) - ❌ 无企业账")

    # Payment 3: 只有订单，没有企业账和总账（不完整）
    payment_no_enterprise_2 = system.create_payment([orders[4].id], "enterprise_A")
    print(f"  Payment {payment_no_enterprise_2.id}: ¥{payment_no_enterprise_2.amount} (订单: {[orders[4].id]}) - ❌ 无企业账")

    # Payment 4: 有企业账但没有总账（不完整）
    payment_no_total = system.create_payment([orders[5].id], "enterprise_C")
    print(f"  Payment {payment_no_total.id}: ¥{payment_no_total.amount} (订单: {[orders[5].id]}) - 有企业账但无总账")

    # 3. 创建部分企业账（故意不创建所有）
    print("\n3. 创建部分企业账（故意不完整）...")

    # 只为Payment 1创建企业账
    enterprise_total_1 = system.create_enterprise_total([payment_complete.id])
    print(f"  企业账单 {enterprise_total_1.id}: ¥{enterprise_total_1.total_amount} (Payment: {[payment_complete.id]})")

    # 为Payment 4创建企业账（但不创建总账）
    enterprise_total_2 = system.create_enterprise_total([payment_no_total.id])
    print(f"  企业账单 {enterprise_total_2.id}: ¥{enterprise_total_2.total_amount} (Payment: {[payment_no_total.id]}) - ❌ 无总账")

    # 4. 创建部分总账（故意不创建所有）
    print("\n4. 创建部分总账（故意不完整）...")

    # 只为enterprise_total_1创建总账
    total_1 = system.create_total_amount([enterprise_total_1.id])
    print(f"  总账单 {total_1.id}: ¥{total_1.total_amount} (企业账: {[enterprise_total_1.id]})")

    # 5. 使用现有函数找出不匹配的数据
    print("\n=== 使用现有函数找出不匹配数据 ===")

    # 获取所有Payment ID
    all_payment_ids = system.get_all_payment_ids()
    print(f"  所有Payment ID: {all_payment_ids}")

    # 5.1 找出没有企业账的Payment
    print("\n🔍 5.1 找出没有企业账的Payment:")
    payments_without_enterprise = system.relationships.get_payments_without_enterprise_total(all_payment_ids)
    print(f"  结果: {payments_without_enterprise}")
    if payments_without_enterprise:
        for pid in payments_without_enterprise:
            payment = system.payments[pid]
            print(f"    - Payment {pid}: ¥{payment.amount}, 企业: {payment.enterprise_id}")

    # 5.2 找出没有总账的EnterpriseTotal
    print("\n🔍 5.2 找出没有总账的EnterpriseTotal:")
    enterprise_totals_without_total = system.relationships.get_enterprise_totals_without_total()
    print(f"  结果: {enterprise_totals_without_total}")
    if enterprise_totals_without_total:
        for ent_id in enterprise_totals_without_total:
            ent = system.enterprise_totals[ent_id]
            print(f"    - 企业账单 {ent_id}: ¥{ent.total_amount}, 企业: {ent.enterprise_id}")

    # 5.3 获取所有不完整的Payment（综合分析）
    print("\n🔍 5.3 获取所有不完整的Payment（综合分析）:")
    incomplete_payments = system.relationships.get_incomplete_payments(all_payment_ids)
    print(f"  缺少企业账的Payment: {incomplete_payments['missing_enterprise_total']}")
    print(f"  缺少总账的Payment: {incomplete_payments['missing_total']}")
    print(f"  完全缺失的Payment: {incomplete_payments['completely_missing']}")

    # 详细展示每个不完整的Payment
    print("\n  详细分析:")
    for pid in incomplete_payments['missing_enterprise_total']:
        payment = system.payments[pid]
        print(f"    ❌ Payment {pid} (¥{payment.amount}, {payment.enterprise_id}): 缺少企业账")

    for pid in incomplete_payments['missing_total']:
        payment = system.payments[pid]
        ent_id = system.relationships.get_enterprise_total_by_payment(pid)
        print(f"    ⚠️  Payment {pid} (¥{payment.amount}, {payment.enterprise_id}): 有企业账 {ent_id} 但缺少总账")

    # 5.4 获取完整性统计
    print("\n🔍 5.4 数据完整性统计:")
    summary = system.relationships.get_completeness_summary()
    print(f"  总Payment数: {summary['total_payments']}")
    print(f"  有企业账的Payment: {summary['payments_with_enterprise']}")
    print(f"  无企业账的Payment: {summary['payments_without_enterprise']}")
    print(f"  总企业账单数: {summary['total_enterprise_totals']}")
    print(f"  有总账的EnterpriseTotal: {summary['enterprise_totals_with_total']}")
    print(f"  无总账的EnterpriseTotal: {summary['enterprise_totals_without_total']}")
    print(f"  总账单数: {summary['total_amounts']}")
    print(f"  完整性比率:")
    print(f"    Payment → 企业账: {summary['completeness_rate']['payment_to_enterprise']}")
    print(f"    企业账 → 总账: {summary['completeness_rate']['enterprise_to_total']}")

    # 5.5 溯源查询验证
    print("\n=== 溯源查询验证 ===")

    # 完整路径的Payment
    print(f"\n完整路径Payment {payment_complete.id}:")
    trace_complete = system.trace_payment_forward(payment_complete.id)
    print(f"  Payment: {trace_complete['payment'].id} (¥{trace_complete['payment'].amount})")
    print(f"  Orders: {[o.id for o in trace_complete['orders']]}")
    print(f"  EnterpriseTotal: {trace_complete['enterprise_total'].id if trace_complete['enterprise_total'] else '❌ 无'}")
    print(f"  TotalAmount: {trace_complete['total_amount'].id if trace_complete['total_amount'] else '❌ 无'}")

    # 缺少企业账的Payment
    print(f"\n缺少企业账的Payment {payment_no_enterprise.id}:")
    trace_incomplete1 = system.trace_payment_forward(payment_no_enterprise.id)
    print(f"  Payment: {trace_incomplete1['payment'].id} (¥{trace_incomplete1['payment'].amount})")
    print(f"  Orders: {[o.id for o in trace_incomplete1['orders']]}")
    print(f"  EnterpriseTotal: {trace_incomplete1['enterprise_total'].id if trace_incomplete1['enterprise_total'] else '❌ 无'}")
    print(f"  TotalAmount: {trace_incomplete1['total_amount'].id if trace_incomplete1['total_amount'] else '❌ 无'}")

    # 有企业账但缺总账的Payment
    print(f"\n有企业账但缺总账的Payment {payment_no_total.id}:")
    trace_incomplete2 = system.trace_payment_forward(payment_no_total.id)
    print(f"  Payment: {trace_incomplete2['payment'].id} (¥{trace_incomplete2['payment'].amount})")
    print(f"  Orders: {[o.id for o in trace_incomplete2['orders']]}")
    print(f"  EnterpriseTotal: {trace_incomplete2['enterprise_total'].id if trace_incomplete2['enterprise_total'] else '❌ 无'}")
    print(f"  TotalAmount: {trace_incomplete2['total_amount'].id if trace_incomplete2['total_amount'] else '❌ 无'}")


if __name__ == "__main__":
    # 运行原始demo
    demo()

    # 运行不匹配案例演示
    demo_incomplete_payments()
