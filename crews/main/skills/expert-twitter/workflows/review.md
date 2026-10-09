# Review
用户临时复盘或已配置周期任务触发时，用 twitter-engagement daily 获取本人作品指标并回填 published-track。核对 account、updates/skipped、来源时间和实际分页；未匹配记录或字段缺项注明，不用其他账号公开值冒充后台指标。通过 published-track query 读取历史，比较同账号同类型内容与相同观察周期；数据不足不归因。调用 content-calibrator 的已支持能力前核对平台支持表，未接入时直接用真实指标给出有证据的人工复盘。报告存 twitter/dna/<dna-id>/evals/，提出下一步测试，用户确认后再更新 DNA/template。
