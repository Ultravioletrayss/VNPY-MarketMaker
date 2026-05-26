1. ScenarioSelector
   先判断当前属于 1-8 档中的哪一档

2. QuoteGenerator
   根据场景参数 + 非本方盘口，生成目标买卖报价

3. RiskManager
   检查目标报价能不能用
   如果盘口无效、深度不足、报价倒挂、价格笼子不通过，就过滤掉

4. OrderManager
   拿“风控通过后的目标报价”
   和“当前已经挂着的做市订单”进行比较
   决定撤单 / 补单 / 重报 / 保持不动

5. 主策略 execute_order_plan()
   根据 OrderManager 生成的 plan，真正执行 buy / short / cancel_order

这个写的很好