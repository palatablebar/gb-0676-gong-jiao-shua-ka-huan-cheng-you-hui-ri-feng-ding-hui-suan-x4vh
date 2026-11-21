# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。企业裁决阶段另返回transfers（前后程对照、责任企业、责任依据、归属差异）、ledger（补偿台账）、enterprise_summary与ruling。/api/upload接收multipart文件file。/api/runs/<id>/reconcile确认企业间账目核清（幂等），核清前日结暂缓封存。/api/runs/<id>/compensations返回该批次补偿台账。/api/runs/<id>/archive只导出一份带清单与证据的CSV，原始刷卡与归属依据随证据保留。
