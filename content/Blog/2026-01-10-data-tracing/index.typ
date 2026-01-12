#import "../index.typ": template, tufted
#show: template

= 数据跟踪系统简单设计与实现

== 业务模型

#{
  ```Order * -- 1 Payment * -- 1 EnterpriceTotalAmount * -- 1 TotalAmount```
}

*业务流程*：
- Order 结算后产生 Payment，Payment会和Order进行匹配
- Payment 根据企业求和后得到企业账 EnterpriceTotalAmount
- EnterpriceTotalAmount 求和后得到总账单 TotalAmount

*核心需求*：
+ Payment会和Order进行匹配
+ 记录企业账来自哪几个Payment
+ 记录总账单来自那个企业账、哪个Payment
+ 从Payment查询，可以跟踪来源的多个订单以及后续的1个企业账单和一个总账单

== 数据结构设计

=== 实体类（纯数据，不包含关系）

```python
@dataclass
class Order:
    """订单实体 - 纯数据，不包含关系"""
    id: str
    amount: float
    enterprise_id: str
    created_at: datetime

@dataclass
class Payment:
    """支付实体 - 纯数据，不包含关系"""
    id: str
    enterprise_id: str    # 所属企业ID
    amount: float
    created_at: datetime

@dataclass
class EnterpriseTotalAmount:
    """企业账单实体 - 纯数据，不包含关系"""
    id: str
    enterprise_id: str
    total_amount: float
    created_at: datetime

@dataclass
class TotalAmount:
    """总账单实体 - 纯数据，不包含关系"""
    id: str
    total_amount: float
    created_at: datetime
```

=== 独立关系映射

```python
@dataclass
class RelationshipMapping:
    """独立的关系映射数据结构"""

    # Payment -> Orders (N:1)
    payment_to_orders: Dict[str, Set[str]]

    # Payment -> EnterpriseTotal (N:1)
    payment_to_enterprise_total: Dict[str, str]

    # EnterpriseTotal -> Payments (1:N)
    enterprise_total_to_payments: Dict[str, Set[str]]

    # EnterpriseTotal -> TotalAmount (N:1)
    enterprise_total_to_total: Dict[str, str]

    # TotalAmount -> EnterpriseTotals (1:N)
    total_to_enterprise_totals: Dict[str, Set[str]]
```

*设计优势*：
- 数据与关系分离，符合单一职责原则
- 易于序列化和存储
- 支持多种存储后端（内存、数据库、图数据库）

== 核心算法实现

=== 1. 数据创建流程

```python
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

    payment = Payment(id=f"PAY-{uuid.uuid4().hex[:8]}", ...)
    self.payments[payment.id] = payment

    # 在独立的关系映射中记录关系
    for order_id in order_ids:
        self.relationships.add_payment_order(payment.id, order_id)

    return payment
```

=== 2. 正向溯源算法

```python
def trace_payment_forward(self, payment_id: str) -> Dict:
    """正向溯源：Payment → Orders → Enterprise → Total"""
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
```

=== 3. 不完整数据检测算法

```python
def get_payments_without_enterprise_total(self, all_payment_ids: Set[str]) -> Set[str]:
    """获取所有未生成企业账单的Payment ID"""
    payments_with_enterprise = set()
    for payment_id in all_payment_ids:
        if payment_id in self.payment_to_enterprise_total:
            ent_id = self.payment_to_enterprise_total[payment_id]
            if ent_id:
                payments_with_enterprise.add(payment_id)
    return all_payment_ids - payments_with_enterprise

def get_incomplete_payments(self, all_payment_ids: Set[str]) -> Dict[str, Set[str]]:
    """获取所有不完整的Payment（缺少企业账单或总账单）"""
    result = {
        "missing_enterprise_total": set(),
        "missing_total": set(),
        "completely_missing": set()
    }

    for payment_id in all_payment_ids:
        ent_id = self.payment_to_enterprise_total.get(payment_id)

        if not ent_id:
            result["missing_enterprise_total"].add(payment_id)
            result["completely_missing"].add(payment_id)
        else:
            total_id = self.enterprise_total_to_total.get(ent_id)
            if not total_id:
                result["missing_total"].add(payment_id)

    return result
```

== 测试案例与结果

=== 测试场景设计

创建4个Payment数据，其中3个为不完整数据：

1. **Payment 1** (`PAY-eb1233a0`): 完整路径（订单 → Payment → 企业账 → 总账）
2. **Payment 2** (`PAY-bcf7e992`): ❌ 缺少企业账和总账
3. **Payment 3** (`PAY-f53a23a2`): ❌ 缺少企业账和总账
4. **Payment 4** (`PAY-7edead79`): ⚠️ 有企业账但缺少总账

=== 检测结果

*5.1 找出没有企业账的Payment*：
```
结果: {'PAY-bcf7e992', 'PAY-f53a23a2'}
- Payment PAY-bcf7e992: ¥400, 企业: enterprise_B
- Payment PAY-f53a23a2: ¥300, 企业: enterprise_A
```

*5.3 综合分析*：
- 缺少企业账的Payment: `{'PAY-bcf7e992', 'PAY-f53a23a2'}`
- 缺少总账的Payment: `{'PAY-7edead79'}`
- 完全缺失的Payment: `{'PAY-bcf7e992', 'PAY-f53a23a2'}`

*5.4 数据完整性统计*：
- 总Payment数: 4
- 有企业账的Payment: 2 (50.0%)
- 无企业账的Payment: 2 (50.0%)
- 企业账 → 总账完整性: 50.0%

=== 溯源查询验证

*完整路径Payment*：
```
Payment: PAY-eb1233a0 (¥300)
Orders: ['ORD-14ee7e25', 'ORD-6224a742']
EnterpriseTotal: ENT-777a7b41
TotalAmount: TOT-ecfe6ea1
```

*缺少企业账的Payment*：
```
Payment: PAY-bcf7e992 (¥400)
Orders: ['ORD-5216f801', 'ORD-12b1e236']
EnterpriseTotal: ❌ 无
TotalAmount: ❌ 无
```

*有企业账但缺总账的Payment*：
```
Payment: PAY-7edead79 (¥400)
Orders: ['ORD-e355b48d']
EnterpriseTotal: ENT-9a95293b
TotalAmount: ❌ 无
```

== 存储方案对比

=== 1. 关系型数据库

*表结构*：
- `orders` 表：id, amount, enterprise_id, created_at
- `payments` 表：id, enterprise_id, amount, created_at
- `enterprise_totals` 表：id, enterprise_id, total_amount, created_at
- `totals` 表：id, total_amount, created_at
- `payment_orders` 表：payment_id, order_id
- `payment_enterprise` 表：payment_id, enterprise_total_id
- `enterprise_total_totals` 表：enterprise_total_id, total_id

*优点*：成熟的事务支持，ACID保证
*缺点*：多表关联查询复杂，性能开销大

=== 2. 图数据库

*节点类型*：Order, Payment, EnterpriseTotal, TotalAmount
*边类型*：CONTAINS, BELONGS_TO, SUMMARIZED_BY

*查询示例*（Cypher）：
```cypher
MATCH (p:Payment {id: 'PAY-123'})-[:CONTAINS]->(o:Order)
MATCH (p)-[:BELONGS_TO]->(et:EnterpriseTotal)
MATCH (et)-[:SUMMARIZED_BY]->(t:TotalAmount)
RETURN p, o, et, t
```

*优点*：天然适合层级关系查询，性能优秀
*缺点*：学习曲线陡峭，生态相对不成熟

=== 3. 独立关系映射（当前方案）

*存储结构*：
```json
{
  "entities": {
    "orders": {"ORD-001": {...}},
    "payments": {"PAY-001": {...}},
    ...
  },
  "relationships": {
    "payment_to_orders": {"PAY-001": ["ORD-001"]},
    "payment_to_enterprise_total": {"PAY-001": "ENT-001"},
    ...
  }
}
```

*优点*：
- 数据与关系完全分离
- 易于序列化和反序列化
- 支持多种后端存储
- 查询逻辑清晰

*缺点*：
- 需要手动维护一致性
- 复杂查询需要多次查找

== 总结

本方案通过**数据与关系分离**的设计模式，实现了灵活的数据溯源系统。核心创新点：

1. **独立关系映射**：将实体数据与关系数据完全分离
2. **完整性检测**：提供多种算法识别数据不完整的情况
3. **双向溯源**：支持正向（Payment→Total）和反向（Total→Payment）查询
4. **存储无关**：支持关系型数据库、图数据库或自定义存储

该方案在实际应用中可以有效识别数据质量问题，为数据治理提供技术支撑。
