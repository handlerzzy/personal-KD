以下是严格从五篇论文中提取的 **100个高质量QA对**，每篇论文各20个。所有问题和答案均直接来源于论文原文内容，并标注了来源章节或图表序号，确保可追溯性。

---

## 第一篇论文：《Quantifying Test Coverage for Retrieval-Augmented Generation Systems》（2510.00001v1）

**Q1:** 本文提出的方法论的主要目标是什么？  
**A1:** 量化RAG测试问题对底层文档的语义覆盖程度，提供实用框架来验证测试的全面性。（来源：Abstract）

**Q2:** 本文方法的核心直觉是什么？  
**A2:** 设计良好的测试问题应在嵌入空间中与相关文档块的聚类“靠近”，确保文档语料中的关键语义区域至少被一个测试问题覆盖。（来源：Conceptual Framework）

**Q3:** 本文使用什么算法识别离群测试问题？  
**A3:** 使用局部离群因子（Local Outlier Factor, LOF）算法，基于与主要文档嵌入的语义距离识别离群问题。（来源：Conceptual Framework 及 Identifying Outlier Questions）

**Q4:** 基础覆盖率（basic coverage）的公式中，mindist(d_i)代表什么？  
**A4:** 每个文档块d_i到所有“inlier”测试问题集合的最小余弦距离。（来源：Coverage Metrics - Basic Coverage）

**Q5:** 加权覆盖率（weighted coverage）与基础覆盖率的主要区别是什么？  
**A5:** 加权覆盖率根据每个聚类的相对大小进行加权，确保语义内容更丰富的区域对总体分数贡献更大。（来源：Coverage Metrics - Weighted Coverage）

**Q6:** 多集群覆盖率（multi-cluster coverage）如何定义问题覆盖集群？  
**A6:** 如果测试问题与集群中心的距离小于可配置的阈值，则认为该问题覆盖该集群。（来源：Coverage Metrics - Multi-Cluster Coverage）

**Q7:** 本文实现的七个步骤工作流包括哪些？  
**A7:** 文档分块、嵌入生成、聚类、离群识别、距离计算、覆盖率计算、差距分析与建议。（来源：Implementation）

**Q8:** 本文使用了哪些嵌入提供商和模型？  
**A8:** OpenAI（text-embedding-3-small, embedding-3-large, ada-002）和Voyage AI（voyage-3）。（来源：Embeddings）

**Q9:** 差距分析中如何识别低覆盖率聚类？  
**A9:** 识别覆盖率低于可配置阈值（默认0.7）的聚类，提取关键主题并生成建议的测试问题。（来源：Gap Analysis）

**Q10:** 论文使用了什么降维技术进行可视化？  
**A10:** t-SNE（t-Distributed Stochastic Neighbor Embedding）。（来源：Visualization）

**Q11:** 第一个真实世界用例（产品文档）初始有多少个文档块和测试问题？  
**A11:** 415个文档块（每个500 tokens）和31个测试问题。（来源：Use Case Descriptions）

**Q12:** 初始分析中，基础覆盖率为69.4%，存在多少个语义聚类存在盲点？  
**A12:** 五个语义聚类中有四个存在盲点。（来源：Use Case Descriptions）

**Q13:** 添加新生成的问题后，基础覆盖率提升到多少？  
**A13:** 77.6%。（来源：Addressing Challenge 1: Incomplete Test Coverage）

**Q14:** 第二个用例中，为了模拟无关内容问题，向Schwab S&P 500基金说明书注入了什么文档？  
**A14:** 一份描述多种鸟类物种的语义无关文档。（来源：Use Case Descriptions 及 Addressing Challenge 2）

**Q15:** 在第二个用例中，“bird species”聚类的覆盖率得分是多少？  
**A15:** 43.2%，显著低于Schwab主题聚类的86.5%和87.4%。（来源：Addressing Challenge 2: Presence of Irrelevant Knowledge）

**Q16:** 本文方法与RAGAS和ARES的核心区别是什么？  
**A16:** 本文关注输入覆盖问题（评估测试集对知识域的覆盖），而非仅评估模型输出质量。（来源：Related Work 及 Conclusion）

**Q17:** 论文指出，LOF算法无法辨别什么问题？  
**A17:** 无法辨别问题之所以不相关的具体原因。（来源：Limitations）

**Q18:** 为什么本文不追求一个“理想”的100%覆盖率？  
**A18:** 100%覆盖率表示测试集与文档块完全句法对齐，这是不期望的状态；覆盖率应是相对度量，用于比较不同的测试集。（来源：Methodology 及 Basic Coverage）

**Q19:** 论文提到了哪个经典的软件测试概念作为类比？  
**A19:** 代码覆盖率（code coverage）。（来源：Introduction）

**Q20:** 论文提出的未来工作方向之一是什么？  
**A20:** 优化测试集效率，集成效率度量来标记冗余问题，减少人工审查成本。（来源：Discussion）

---

## 第二篇论文：《SeedER: Seed-and-Expand Retrieval from Knowledge Graphs》（2605.23753v1）

**Q1:** SEEDER的全称是什么？  
**A1:** Seed-and-Expand Retrieval。（来源：Title 及 Abstract）

**Q2:** SEEDER如何解决组合式图查询的检索难题？  
**A2:** 将全局推理分解为可重用的局部决策，通过迭代、低成本扩展实现高效发现与查询相关的节点，同时严格控制扩展成本。（来源：Abstract）

**Q3:** 论文证明密集检索在什么情况下需要Ω(|V|)的嵌入大小？  
**A3:** 在一种特定形式的关系追踪图（relation-tracing graph）上，任何基于固定查询和节点嵌入的密集检索方法都需要Ω(|V|)的嵌入大小才能正确回答。（来源：Section 3 - Hardness of dense retrieval）

**Q4:** K-HOP-WITH-FILTERING的评分函数中，候选节点u的分数如何计算？  
**A4:** score(u) = 1/3·sim(q, u) + max_{v→u, v∈F} 1/3·sim(q, v) + 1/3·sim(q, r)，其中F是当前前沿节点集合，r是连接关系。（来源：Section 3 - A practical neighborhood-based expansion algorithm）

**Q5:** 命题B.9（Proposition B.9）证明了什么？  
**A5:** 即使目标函数是单调子模的，纯贪心策略局限于前沿节点也可能比最优可达集合表现任意差。（来源：Section 4 - Proposition B.9: Failure of frontier-greedy policies）

**Q6:** SEEDER的RL策略使用什么方法降低方差？  
**A6:** 使用同一查询采样的多个轨迹的均值作为基线，计算优势函数（减去均值）。（来源：Section 4 - RL Formulation）

**Q7:** 论文在STARK-PRIME上使用哪种文本编码器进行主要实验？  
**A7:** MiniLM-L6-v2。（来源：Main Results 及 Table 1）

**Q8:** 在STARK-PRIME上，SEEDER相比密集检索在Hit@5上提升了多少？  
**A8:** 从0.218提升到0.411。（来源：Table 1）

**Q9:** 在STARK-PRIME上使用Qwen3-Embedding-4B时，SEEDER的Recall@20达到多少？  
**A9:** 0.647。（来源：Table 2a）

**Q10:** SEEDER的可训练参数量约为多少？与GraphFlow相比如何？  
**A10:** 1.1M可训练参数，约为GraphFlow（8B参数LLM）的1/8000。（来源：Latency and Memory Comparison 及 Figure 4）

**Q11:** 消融研究中，移除最终评分头（scoring head）后Hit@1从0.199下降到多少？  
**A11:** 0.059。（来源：Table 2b - “No auxiliary loss”）

**Q12:** STARK-PRIME知识图谱包含多少种节点类型和边？  
**A12:** 10种节点类型（包括disease, drug, gene等）和8.1M条有向类型边。（来源：Section 2 - Background and Problem Setting 及 Appendix A）

**Q13:** 论文使用什么方法进行最终节点排名？  
**A13:** 通过GNN产生的两分类logit的差值作为检索分数：s_θ(q,v) = logit_θ(v,1) - logit_θ(v,0)。（来源：Appendix D.5 - Final Node Scores）

**Q14:** SEEDER在训练时如何限制搜索空间？  
**A14:** 首先使用K-HOP-WITH-FILTERING从初始种子节点提取中等大小的查询特定子图（通常100-200节点），作为RL策略的有界搜索环境。（来源：Section 4 - Bounded Search Space Construction）

**Q15:** 论文中使用的GNN编码器架构是什么？  
**A15:** 稀疏图Transformer，受Exphormer架构启发，但注意力仅限于观察到的KG邻域的稀疏拓扑，不添加expander边。（来源：Appendix D.2 - Sparse Graph Transformer Encoder）

**Q16:** 在STARK-AMAZON数据集上，SEEDER的Hit@1是多少？  
**A16:** 0.319。（来源：Table 1）

**Q17:** 论文中PRM（Process Reward Model）基线的作用是什么？  
**A17:** 学习一个奖励模型来评分图搜索中的中间状态-动作对，引导代理做出更优的下一步决策。（来源：Appendix E - PRM）

**Q18:** SEEDER与LLM-based agentic方法（如GraphFlow）相比的主要优势是什么？  
**A18:** 更轻量级（1.1M vs 8B参数），每查询延迟低几十倍，同时仍能恢复大部分性能增益。（来源：Latency and Memory Comparison）

**Q19:** 图6（Figure 6）显示K-HOP-WITH-FILTERING在哪个数据集上增益最小？  
**A19:** STARK-AMAZON，因为密集检索本身已经很强，限制了图发现算法的改进空间。（来源：Appendix F.2 - Budgeted K-Hop Filtering Across Metrics）

**Q20:** 论文的理论分析中，为什么迭代局部策略在样本复杂度上优于单一体检索器？  
**A20:** 迭代局部学习器只需要学习如何执行每个局部步骤，然后可以组合这些步骤实现组合泛化；而单一体检索器必须学习完整的映射，复杂度高得多。（来源：Section 3 - 理论对比及Proposition B.7）

---

## 第三篇论文：《LLM-Driven Design of Physics-Constrained Constitutive Models: Two Agents Are Better Than One》（2605.23754v1）

**Q1:** 本文提出的多智能体架构中，Creator被要求强制满足几个物理约束？  
**A1:** 九个物理约束。（来源：Abstract 及 Section 2.3）

**Q2:** 论文验证的九个物理约束中，哪一个是由于不可压缩性而自动满足的？  
**A2:** 增长条件（growth condition），因为在不可压缩约束J=1下，所有可接受变形都满足J=1。（来源：Section 2.3 - Growth condition 及 Appendix A.7）

**Q3:** 本文使用什么方法验证热力学一致性？  
**A3:** 测试两个封闭变形环路上的四个指标：归一化环路残差、应力唯一性，以及两个开放路径之间的工作一致性和逐点功-能一致性。（来源：Appendix A.2 - Thermodynamic consistency）

**Q4:** GenCANN与本文方法的关键差距是什么？  
**A4:** GenCANN不提供任何系统性的检查来验证生成的网络是否满足物理约束。（来源：Section 3 - “What GenCANN does not provide, however, is any systematic check that the generated networks satisfy the physical constraints”）

**Q5:** 在Claude Opus 4.7上，Creator alone的物理约束通过率是多少？  
**A5:** 91%。（来源：Section 4.1 - Figure 4）

**Q6:** 在Kimi K2.5上，加入Inspector后真正满足约束的模型比例从37%提升到多少？  
**A6:** 56%。（来源：Section 4.1 - Figure 4）

**Q7:** Opus Inspector（无工具）将模型标记为违反时，实际违反的比例是多少？  
**A7:** 100%（即所有标记违反的模型确实违反）。（来源：Section 4.2 - “Of the models that the Opus Inspector (without tools) flags as violating, 100% in fact adhere to the physical constraints.”）

**Q8:** Kimi Inspector在有工具访问时表现出什么调用模式？  
**A8:** 双峰模式：要么调用所有可用工具，要么一个都不调用。（来源：Section 4.2 - Figure 5 及描述）

**Q9:** 对于Opus-powered Creator-Inspector对，新违规在下一轮被解决的比例是多少？  
**A9:** 93%。（来源：Section 4.3 - Figure 6 及分析）

**Q10:** 论文使用了哪三个基准数据集进行验证？  
**A10:** 脑组织（human cerebral tissue）、实验橡胶（Treloar）和合成橡胶。（来源：Section 3.5 - Benchmark problems）

**Q11:** 脑组织数据集包含多少个应力-应变点？  
**A11:** 每个加载模式仅报告17个点。（来源：Section 3.5 - “Only 17 stress-strain points are reported per loading mode”）

**Q12:** 在合成橡胶数据上，Opus生成模型在Treloar不变平面上的相对误差如何？  
**A12:** 相对误差保持在5%以下。（来源：Section 4.6 - Figure 8d 及描述）

**Q13:** 论文中用于评估泛化和外推能力的Treloar不变平面覆盖了哪些加载路径？  
**A13:** 从未单轴到等双轴拉伸，纯剪切位于角中点，同时评估插值（泛化）和外推。（来源：Section 4.6）

**Q14:** Kimi K2.5生成的橡胶模型网络大小与基线相比如何？  
**A14:** Kimi倾向于生成更大的网络（例如合成橡胶使用256,256，基线为16,16）。（来源：Section 4.7 - Table 1）

**Q15:** 图12显示，在脑组织数据上，第一次精炼后精度有何变化？  
**A15:** 第一次精炼后有小的改进，第二次精炼没有进一步改进。（来源：Section 4.9 - Figure 12 及分析）

**Q16:** 论文中Creator-Inspector精炼循环执行几次？  
**A16:** 初始生成后再执行两次精炼，每轮输出三个Inspector批准的模型，选择最准确的作为最终输出。（来源：Section 3.2 - Pipeline）

**Q17:** 论文使用什么方法在训练时从前沿节点采样子集？  
**A17:** 使用Gumbel-Softmax或Gumbel-top-k采样，温度τ控制随机性。（来源：Section 4 - 及 Appendix D.3 - Stochastic Expansion with Gumbel-Softmax）

**Q18:** 对于脑组织数据，人类专家设计的基线CANN来自哪项工作？  
**A18:** Pierre et al. (2023a) 的最准确CANN。（来源：Figure 10 标题）

**Q19:** 论文中提到的“苦涩教训”（bitter lesson）是指什么？  
**A19:** 通用方法随计算量扩展最终会超越依赖手工领域知识的方法。（来源：Section 5.3 - “In the spirit of Sutton's bitter lesson”）

**Q20:** 论文的代码和数据仓库地址是什么？  
**A20:** https://github.com/AgenticModeling/MultiAgentConstitutiveModeling26 （来源：Declarations - Software and data availability）

---

## 第四篇论文：《Debiased Negative Mining Improves Out-of-distribution Detection with Pre-trained Vision-Language Models》（2605.23797v1）

**Q1:** 本文针对现有VLM-based OOD检测方法中的什么问题提出解决方案？  
**A1:** 负标签挖掘中的假阴性问题（false negative problem），导致有偏的OOD评分函数。（来源：Introduction）

**Q2:** 本文的核心方法是什么？  
**A2:** 通过间接逼近负标签的真实分布来校正采样偏差，转化为基于正标签和未标记野生语料数据的蒙特卡洛采样。（来源：Introduction 及 Section 4）

**Q3:** 定理1（Theorem 1）证明了什么？  
**A3:** 当负标签数量r→∞时，无偏OOD评分函数S_unbiased(x;f)收敛到\hat{S}_unbiased(x;f) = (Σe^h) / (Σe^h + λ·E[e^h])。（来源：Section 4 - Theorem 1）

**Q4:** 本文使用的评价指标FPR95的定义是什么？  
**A4:** 当ID数据的真正例率达到95%时，OOD数据的假正例率。（来源：Section 6 - Evaluation Metrics）

**Q5:** 在ImageNet-1K作为ID、ViT B/16 CLIP编码器下，本文方法在iNaturalist上的AUROC和FPR95是多少？  
**A5:** AUROC 99.51，FPR95 1.78。（来源：Table 1）

**Q6:** 本文如何模拟正标签的嵌入？  
**A6:** 对每个ID标签的文本嵌入应用Ω(z) = l₂(z + σ·e)，其中e ~ N(0, I_d)，σ为高斯噪声强度。（来源：Section 5 - Step 2）

**Q7:** 如何从未标记野生语料中选择代表性样本？  
**A7:** 基于α最近邻的密度：Rep(˜y_i) = -log Σ_{˜y_j∈M(˜y_i,α)} ||˜y_i - ˜y_j||₂²，选择密度最高的样本。（来源：Section 5 - Step 1）

**Q8:** 本文的理论框架中，野生数据分布Q_Y如何分解？  
**A8:** Q_Y = τ·P_Y⁺ + (1-τ)·P_Y⁻，其中τ是先验概率，P_Y⁺为正标签分布，P_Y⁻为负标签分布。（来源：Definition 1 - Wild Data Distribution）

**Q9:** 定理2（Theorem 2）给出了什么界限？  
**A9:** 偏差δ(x;f)的期望上界为：E[δ] ≤ (1/(1-τ))·√(πe^{3κ}/(2m)) + (τ/(1-τ))·√(πe^{3κ}/(2n))。（来源：Theorem 2）

**Q10:** 本文在消融研究中测试了哪些CLIP视觉编码器架构？  
**A10:** ViT-B/32、ViT-L/14和ResNet-50。（来源：Table 2）

**Q11:** 在336×336分辨率下，本文方法在SUN数据集上的AUROC比NegLabel高多少？  
**A11:** 96.29 vs 95.68（提升0.61）。（来源：Table 3）

**Q12:** 本文使用的未标记野生语料来源是什么？  
**A12:** WordNet。（来源：Implementation）

**Q13:** 当L（采样的野生标签数量）增加时，OOD检测性能如何变化？  
**A13:** 性能改善，这与定理2的分析一致。（来源：Section 6.3 - Hyper-parameter Analysis 及 Figure 2）

**Q14:** 本文方法与NegLabel在“Common”语料源上的平均AUROC对比如何？  
**A14:** 本文为90.34，NegLabel为89.29。（来源：Table 4）

**Q15:** 本文中温度参数κ的默认值是多少？  
**A15:** κ = 0.01。（来源：Implementation）

**Q16:** 本文方法在ImageNet-1K上的平均FPR95（四个OOD数据集平均）是多少？  
**A16:** 16.90%。（来源：Table 1 - Average列）

**Q17:** 论文中对比的“traditional visual OOD detection methods”包括哪些？  
**A17:** MSP、ODIN、Energy、GradNorm、ViM、KNN、VOS、NPOS、LSN等。（来源：Table 1 上部）

**Q18:** 论文认为CLIP在零样本OOD检测中表现出色的原因是什么？  
**A18:** CLIP通过在大型图像-文本数据集上的预训练，能够以细粒度方式解析图像。（来源：Section 6.1 - Main Results）

**Q19:** 论文中使用的“grouping strategy”的作用是什么？  
**A19:** 将过滤后的野生标签分为B个非重叠组，对每组分别计算去偏OOD分数后取平均。（来源：Section 5 - Step 3 及 Eq. 16）

**Q20:** 论文代码仓库地址在哪里？  
**A20:** https://github.com/ 论文中写为“here”，实际链接需参考原文；作者提供了“Code is publicly available at here”的声明。（来源：Abstract）

---

## 第五篇论文：《It's the Humans, Not the Data: Geopolitical Bias in LLMs Originates in Post-Training, Amplified by the Language of the Prompt》（2605.23825v1）

**Q1:** 本文测试了来自几个AI实验室的多少对模型（base和chat）？  
**A1:** 7个实验室的7对模型，共14个模型。（来源：Methods - Models）

**Q2:** 本文使用的7个模型系列中，西方制造的包括哪些？  
**A2:** Mistral 7B（法国）、LLaMA 3 8B（美国）、Gemma 4 8B（美国）。（来源：Methods - Models）

**Q3:** 中国制造的模型系列包括哪些？  
**A3:** Qwen 2.5 7B（阿里巴巴）、Baichuan 2 7B、Yi 1.5 9B（01.AI）、GLM 4 9B（智谱AI/清华）。（来源：Methods - Models）

**Q4:** Qwen 2.5基座模型在中国偏好上的log-odds是多少？  
**A4:** -0.15（p=0.15，与中性无显著差异）。（来源：Results - “Bias Is Created by Post-Training, Not Pretraining”）

**Q5:** Qwen 2.5聊天模型在中国偏好上的log-odds是多少？  
**A5:** +2.91（p<10⁻⁴）。（来源：同上）

**Q6:** 后训练后，3/3西方实验室的模型方向如何变化？  
**A6:** 向反中国方向偏移（Δ = -0.72 到 -2.04）。（来源：Results - “Direction tracks the maker for 6 of 7 families” 及 Figure 1B）

**Q7:** 哪个中国实验室的模型在后训练后出现反中国偏移？  
**A7:** 01.AI的Yi 1.5（Δ = -0.25）。（来源：同上）

**Q8:** Mistral 7B-instruct在法语提示下对法国的偏好变化是多少？  
**A8:** 从英语的-1.46变为法语的+0.45，FR-EN差异+1.91（p<10⁻⁴）。（来源：Results - “The French-prompt Effect”）

**Q9:** 论文中使用什么指标来量化模型偏好？  
**A9:** log-odds，即log P(A) - log P(B)，正值表示偏好国家A。（来源：Methods - Measurement）

**Q10:** 本文验证模型偏好的“coherence filter”标准是什么？  
**A10:** 一个真正的亲X国偏见应该在“更正当”和“更不正当”两种问法中符号相反；保留≥70%模型×语言组合满足符号翻转的场景。（来源：Methods - Coherence Filter）

**Q11:** GLM 4 chat在强制选择中的第一token分布是什么？  
**A11:** P(newline) = 1.0000，即输出单个换行符，这是一种响应开头模板而非拒绝。（来源：Results - “Response-Format Heterogeneity at the First Token” 及 Figure B1）

**Q12:** 如何对Yi 1.5 chat进行prefill校正？  
**A12:** 预填充“（”字符，恢复其verbose回答格式的合规性。（来源：Results - “Response-Format Heterogeneity at the First Token”）

**Q13:** 在开放生成验证中，Qwen的字母选择平均为+0.03但提交位置log-odds为+0.84，解释是什么？  
**A13:** Qwen的贪婪解码倾向选择位置B（无论哪个国家），但偏好体现在提交位置的条件log-odds中。（来源：Appendix A.4 - Free-generation: per-family mechanisms）

**Q14:** 论文进行了哪三种鲁棒性消融实验？  
**A14:** 中性前缀消融、措辞变化消融、跨提示语言因子分解。（来源：Robustness: Hedge, Phrasing, Cross-Prompting 及 Figure 4）

**Q15:** 对于Mistral，跨提示分解显示语言效应主要来自哪个部分？  
**A15:** 场景叙述语言（scenario language）承担了几乎全部效应；ZH场景/EN问题给出-0.03，接近ZH/ZH的-0.07。（来源：Robustness - Cross-prompting factorial 及 Figure 4C）

**Q16:** 当添加“尽可能中立”的系统消息后，Qwen的中国偏好减弱了多少？  
**A16:** 正当问题从+3.09降至+1.37（减少约56%），不正当问题从-3.11降至-1.99（减少约36%）。（来源：Robustness - “Qwen's pro-China preference survives an explicit neutralization instruction”）

**Q17:** 本文使用什么虚构国家名称来测试模型对纯语音线索的响应？  
**A17:** Zhaodong（中文语音）、Bretherland（盎格鲁）、Al-Nuriyah（阿拉伯）、Korvachev（斯拉夫），以及四个无特定身份的虚构名称。（来源：Robustness: Fictional Names Carry Phonetic Identity 及 Appendix C）

**Q18:** 在七款后训练模型中，哪款模型在法语提示下唯一出现正面的法国偏好？  
**A18:** Mistral 7B-instruct。（来源：Results - “The French-prompt Effect”）

**Q19:** 论文中对中国实验室的后训练方向做了哪些统计检验？  
**A19:** 二项检验（6/7，p=0.125）和符号幅度单样本t检验（t=2.78，p=0.032）。（来源：Discussion 及 Appendix A.3）

**Q20:** 论文认为主要局限性之一是什么？  
**A20:** 跨实验室结论基于7个模型系列，统计效力有限；且中文和法文翻译由LLM（Claude）完成而非专业翻译，可能存在循环性。（来源：Limitations）

---

