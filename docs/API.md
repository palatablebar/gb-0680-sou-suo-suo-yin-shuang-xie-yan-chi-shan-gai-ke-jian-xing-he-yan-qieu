# 接口

模块GET使用仓内样例，模块POST可传csv或rows与context，直接计算当前规则。/api/runs使用完整流水线并原子保存。每个阶段返回rows、quarantine、metrics；后续阶段还返回累计隔离。/api/upload接收multipart文件file。/api/runs/<id>/archive只导出一份带清单与证据的CSV。

## 同一性裁决字段

M3（versions）行含 `_fingerprint`（业务正文规范指纹）、`equivalent_duplicate_events`；同版本真实冲突的隔离行含 `conflict_diff`（路径+差异类型）与 `conflict_evidence`（锚事件/当前事件原始 document、指纹集合），metrics 增加 `conflict_groups`、`equivalent_merges`。M4（visibility）行含 `source_document`/`index_document` 双端原文、`source_fingerprint`/`index_fingerprint` 与 `content_diff`，metrics 增加 `content_mismatches`。这些字段原样进入归档 CSV 的 evidence 列。规范指纹只用于裁决与对照，不替换任何原始正文。
