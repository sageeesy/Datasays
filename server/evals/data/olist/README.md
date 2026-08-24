# Olist 2017 Benchmark Fixtures

[中文](#中文说明) | [English](#english)

## 中文说明

本目录中的五张 CSV 派生自 **Brazilian E-Commerce Public Dataset by Olist**：

- 来源：https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- 数据所有者：Olist
- 原始数据许可：CC BY-NC-SA 4.0
- 精简范围：2017 自然年内的 15,000 笔客户级确定性抽样订单，以及完整关联的订单明细、支付、评价、客户地区和商品记录

转换逻辑位于 `server/evals/prepare_olist_benchmark.py`。脚本将原始数据筛选到 2017 下单范围，按 `customer_unique_id` 的 SHA-256 结果稳定抽样客户并保留入选客户的所有订单，再按外键筛选关联表。脚本还会把稳定客户标识和地区字段关联到订单表，翻译可匹配品类，并用“是否存在评价正文”的布尔字段替代原始评价文本。脚本不会生成虚构交易数值。

这些精简数据文件继续遵守原始数据的 CC BY-NC-SA 4.0 条款。DataSays 代码本身的许可状态在仓库根目录单独说明。

## English

These five CSV files are derived from the **Brazilian E-Commerce Public Dataset by Olist**:

- Source: https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- Dataset owner: Olist
- Source license: CC BY-NC-SA 4.0
- Prepared scope: a deterministic customer-level sample of 15,000 orders purchased during calendar year 2017 and their complete related item, payment, review, customer-region, and product records

Transformations are implemented in `server/evals/prepare_olist_benchmark.py`. They filter the source to purchase-year 2017, rank customers by a stable SHA-256 hash of `customer_unique_id`, retain every order for selected customers, and filter child tables by foreign key. They also attach stable customer and region fields to orders, translate available product categories to English, and replace review text with a boolean comment-presence field. No synthetic transaction values are introduced.

These prepared data files retain the source dataset's CC BY-NC-SA 4.0 terms. The licensing status of DataSays source code is documented separately at the repository root.
