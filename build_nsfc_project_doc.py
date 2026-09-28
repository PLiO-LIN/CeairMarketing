from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output" / "丽娃谷风_东方航空智能营销平台_项目文档_V1.5.docx"

BLACK = "000000"
GRAY = "666666"
LIGHT_GRAY = "F2F2F2"
TABLE_WIDTH = 9000


def set_run_font(run, east_asia="宋体", size=12, bold=False, color=BLACK):
    run.font.name = east_asia
    run._element.rPr.rFonts.set(qn("w:eastAsia"), east_asia)
    run._element.rPr.rFonts.set(qn("w:ascii"), "Times New Roman")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Times New Roman")
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def set_paragraph(paragraph, before=0, after=0, line=1.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY,
                  first_indent=True, keep_next=False):
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line
    fmt.keep_with_next = keep_next
    if first_indent:
        fmt.first_line_indent = Cm(0.74)
    else:
        fmt.first_line_indent = Cm(0)
    paragraph.alignment = align


def add_text(doc, text, size=12, font="宋体", bold=False, before=0, after=0,
             line=1.5, align=WD_ALIGN_PARAGRAPH.JUSTIFY, first_indent=True,
             color=BLACK, keep_next=False):
    p = doc.add_paragraph()
    set_paragraph(p, before, after, line, align, first_indent, keep_next)
    set_run_font(p.add_run(text), font, size, bold, color)
    return p


def add_label_text(doc, label, text, before=0, after=0):
    p = doc.add_paragraph()
    set_paragraph(p, before, after, 1.5, WD_ALIGN_PARAGRAPH.JUSTIFY, True)
    set_run_font(p.add_run(label), "黑体", 12, True)
    set_run_font(p.add_run(text), "宋体", 12)
    return p


def add_heading(doc, text, level):
    p = doc.add_paragraph(style=f"Heading {level}")
    if level == 1:
        set_paragraph(p, before=15, after=7, line=1.25, align=WD_ALIGN_PARAGRAPH.LEFT,
                      first_indent=False, keep_next=True)
        set_run_font(p.add_run(text), "黑体", 16, True)
    elif level == 2:
        set_paragraph(p, before=10, after=4, line=1.25, align=WD_ALIGN_PARAGRAPH.LEFT,
                      first_indent=False, keep_next=True)
        set_run_font(p.add_run(text), "黑体", 13, True)
    else:
        set_paragraph(p, before=7, after=2, line=1.25, align=WD_ALIGN_PARAGRAPH.LEFT,
                      first_indent=False, keep_next=True)
        set_run_font(p.add_run(text), "楷体", 12, True)
    return p


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_width(cell, width):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_w = tc_pr.find(qn("w:tcW"))
    if tc_w is None:
        tc_w = OxmlElement("w:tcW")
        tc_pr.append(tc_w)
    tc_w.set(qn("w:w"), str(width))
    tc_w.set(qn("w:type"), "dxa")


def set_cell_margins(cell, top=80, start=90, bottom=80, end=90):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for side, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_row_no_split(row):
    tr_pr = row._tr.get_or_add_trPr()
    node = OxmlElement("w:cantSplit")
    tr_pr.append(node)


def set_repeat_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    node = OxmlElement("w:tblHeader")
    node.set(qn("w:val"), "true")
    tr_pr.append(node)


def set_table_geometry(table, widths):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_layout = tbl_pr.first_child_found_in("w:tblLayout")
    if tbl_layout is None:
        tbl_layout = OxmlElement("w:tblLayout")
        tbl_pr.append(tbl_layout)
    tbl_layout.set(qn("w:type"), "fixed")
    tbl_ind = tbl_pr.first_child_found_in("w:tblInd")
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "0")
    tbl_ind.set(qn("w:type"), "dxa")
    for col, width in zip(table._tbl.tblGrid.gridCol_lst, widths):
        col.set(qn("w:w"), str(width))
    for row in table.rows:
        set_row_no_split(row)
        for cell, width in zip(row.cells, widths):
            set_cell_width(cell, width)
            set_cell_margins(cell)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def add_table(doc, rows, widths, font_size=10.5, header=True):
    if sum(widths) != TABLE_WIDTH:
        raise ValueError(f"Table widths must equal {TABLE_WIDTH}: {widths}")
    table = doc.add_table(rows=len(rows), cols=len(widths))
    table.style = "Table Grid"
    set_table_geometry(table, widths)
    for r_idx, values in enumerate(rows):
        for c_idx, value in enumerate(values):
            cell = table.cell(r_idx, c_idx)
            cell.text = ""
            p = cell.paragraphs[0]
            align = WD_ALIGN_PARAGRAPH.CENTER if r_idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
            set_paragraph(p, before=0, after=0, line=1.18, align=align, first_indent=False)
            set_run_font(p.add_run(value), "宋体", font_size, header and r_idx == 0)
            if header and r_idx == 0:
                set_cell_shading(cell, LIGHT_GRAY)
    if header:
        set_repeat_header(table.rows[0])
    add_text(doc, "", size=4, before=1, after=1, line=1.0, first_indent=False)
    return table


def add_page_field(paragraph):
    field = OxmlElement("w:fldSimple")
    field.set(qn("w:instr"), "PAGE")
    paragraph._p.append(field)


def add_bottom_border(paragraph):
    p_pr = paragraph._p.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "5")
    bottom.set(qn("w:color"), BLACK)
    borders.append(bottom)
    p_pr.append(borders)


def configure_section(section):
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.54)
    section.right_margin = Cm(2.54)
    section.header_distance = Cm(1.25)
    section.footer_distance = Cm(1.25)
    section.different_first_page_header_footer = False
    header = section.header.paragraphs[0]
    set_paragraph(header, before=0, after=0, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    set_run_font(header.add_run("东方航空智能营销平台"), "宋体", 9, False)
    add_bottom_border(header)
    footer = section.footer.paragraphs[0]
    set_paragraph(footer, before=0, after=0, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    set_run_font(footer.add_run("第 "), "宋体", 9, False, GRAY)
    add_page_field(footer)
    set_run_font(footer.add_run(" 页"), "宋体", 9, False, GRAY)


def configure_styles(doc):
    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(12)
    for style_name, font_name, size in (("Heading 1", "黑体", 16), ("Heading 2", "黑体", 13), ("Heading 3", "楷体", 12)):
        style = doc.styles[style_name]
        style.font.name = font_name
        style._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
        style.font.size = Pt(size)
        style.font.color.rgb = RGBColor(0, 0, 0)


def cover(doc):
    add_text(doc, "", size=10, before=44, after=0, line=1.0, first_indent=False)
    add_text(doc, "第八届中国研究生人工智能创新大赛", size=21, font="黑体", bold=True,
             after=54, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    add_text(doc, "东方航空智能营销平台", size=27, font="黑体", bold=True,
             after=16, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    add_text(doc, "项目文档", size=20, font="黑体", bold=True,
             after=38, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    add_text(doc, "V1.5", size=14, font="黑体", bold=True,
             after=45, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    add_text(doc, "2026.08.31", size=13, font="宋体", bold=True,
             after=11, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    add_text(doc, "团队名称：丽娃谷风", size=13, font="宋体", bold=True,
             after=7, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    add_text(doc, "团队成员：胡于飞、林李洋、张婷婷", size=13, font="宋体", bold=True,
             after=7, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    add_text(doc, "参赛组别：以报名系统登记信息为准", size=11, font="宋体",
             after=0, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    doc.add_page_break()


def toc(doc):
    add_text(doc, "目录", size=21, font="黑体", bold=True, before=10, after=20,
             line=1.0, align=WD_ALIGN_PARAGRAPH.LEFT, first_indent=False)
    entries = [
        ("1  项目概况", 0),
        ("1.1  背景和基础", 1),
        ("1.2  场景和价值", 1),
        ("1.3  所需支持", 1),
        ("2  项目规划", 0),
        ("2.1  整体目标", 1),
        ("2.2  技术创新点", 1),
        ("3  实施方案", 0),
        ("3.1  技术可行性分析", 1),
        ("3.2  技术细节", 1),
        ("3.3  计划和分工", 1),
        ("4  参考资料", 0),
    ]
    for text, indent in entries:
        p = add_text(doc, text, size=12, font="宋体", bold=indent == 0,
                     before=0, after=8, line=1.25, align=WD_ALIGN_PARAGRAPH.LEFT,
                     first_indent=False)
        p.paragraph_format.left_indent = Cm(0.75 * indent)
    add_text(doc, "注：目录页码可在 Microsoft Word 中使用“更新域”同步。", size=9.5,
             before=12, line=1.0, align=WD_ALIGN_PARAGRAPH.LEFT, first_indent=False, color=GRAY)
    doc.add_page_break()


def revision_history(doc):
    add_text(doc, "记录更改历史", size=20, font="黑体", bold=True, before=8, after=18,
             line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False)
    rows = [
        ["序号", "更改原因", "版本", "作者", "更改日期", "备注"],
        ["1", "完成项目文档初稿", "V1.0", "丽娃谷风", "2026.08.31", "建立项目论证框架"],
        ["2", "补充本体、推理和稳健性验证", "V1.3", "丽娃谷风", "2026.08.31", "完善 AI Inference 证据"],
        ["3", "按基金申请书式正文提升并保持竞赛模板章节", "V1.4", "丽娃谷风", "2026.08.31", "本版"],
        ["4", "扩展研究方法、技术细节与场景论证", "V1.5", "丽娃谷风", "2026.08.31", "篇幅与内容同步提升"],
    ]
    add_table(doc, rows, [650, 2500, 850, 1300, 1500, 2200], font_size=10.5)
    add_text(doc, "说明：V1.5 保持赛事项目文档模板规定的一级、二级章节；正文采用研究问题牵引、目标可验证、证据可追溯的申请书式论证方式。", size=10.5,
             before=9, after=0, line=1.35, align=WD_ALIGN_PARAGRAPH.JUSTIFY, first_indent=True)
    doc.add_page_break()


def expanded_context(doc):
    add_heading(doc, "1.1.3  相关技术路径比较与研究切入点", 3)
    add_text(doc, "目前面向营销场景的智能化方案大致可分为规则驱动、数据分析驱动、检索增强生成和工作流智能体四类。规则系统能够提供较强的确定性，但在面对跨文档、跨对象和跨时间窗口的信息时，规则维护成本较高；数据分析系统能够发现趋势和分群结果，但难以直接解释复杂业务关系并组织跨部门的营销动作；检索增强生成能够改善回答的事实依据，却常停留在“检索片段加文本回答”的层面；工作流智能体能够完成多步骤调用，但若缺乏领域语义和责任边界，仍可能把形式正确的调用串联成业务上不成立的结论。", after=5)
    comparison_rows = [
        ["技术路径", "适用能力", "在航空营销中仍需解决的问题"],
        ["规则与报表", "适合库存、资格、频控、价格和审批等确定性检查。", "难以自动吸收新文档、新热点和跨对象证据；规则之间的语义关联不足。"],
        ["数据分析与画像", "适合发现客群、趋势、漏斗和经营异常。", "分析结果与产品、活动、渠道、审批及复盘对象之间的业务链条不完整。"],
        ["检索增强生成", "适合从知识片段中回答问题、解释术语、生成初步摘要。", "仅有片段引用不足以表达对象关系、有效期、授权边界与业务动作责任。"],
        ["智能体工作流", "适合组织多轮模型、检索和工具调用，处理复杂任务。", "需要明确工具权限、输出结构、失败策略、人工门禁及全过程审计。"],
    ]
    add_table(doc, comparison_rows, [1800, 3100, 4100])
    add_text(doc, "本项目的切入点不是选择其中某一种技术替代全部能力，而是建立分工明确的协同机制：确定性规则负责不可违反的业务约束，知识库保存原始证据，本体描述可推理的业务语义，Harness 负责受控调用与审计，大模型负责在这些边界内完成归纳、抽取、解释和候选方案生成。这样既避免将所有决策交给模型，也避免把 AI 限缩为不能利用上下文的单轮问答工具。", after=5)
    add_text(doc, "从研究方法看，平台不以“回答是否流畅”作为主要效果标准，而将模型输出置于业务对象链中评价：一项机会建议必须能够关联市场信号、航线/航班、时间窗与客群；一项产品建议必须能够关联资格、库存、有效期和权益事实；一项活动建议必须能够关联预算、频控、渠道与审批；一项复盘建议必须能够关联执行反馈与归因口径。由此形成从语义表示到推理运行、再到业务验证的完整研究闭环。", after=5)

    add_heading(doc, "1.1.4  研究假设与验证逻辑", 3)
    add_label_text(doc, "研究假设 H1：", "当营销材料以“对象—关系—证据—状态”的本体结构而非孤立文本片段提供给模型时，模型输出的证据可定位性、关系完整性和人工审核效率将优于仅依赖自由文本上下文的方式。验证时将比较是否能够回溯到来源、是否能说明对象之间的业务关系，以及人工审核人员完成核对所需的修改和说明。")
    add_label_text(doc, "研究假设 H2：", "当模型调用被嵌入统一 Harness，并同时施加权限、工具白名单、结构 Schema、业务规则和人工确认门禁时，系统能够将异常输入、越权访问、响应缺失、瞬时服务错误和不合规候选限制在可诊断、可回退的范围内。验证时以自动化稳健性测试、运行事件和失败处理记录作为依据。")
    add_label_text(doc, "研究假设 H3：", "本地基于 Qwen 的自研模型并不需要在全部任务上一次性取代云端服务；只要在同一上下文、同一工具与同一门禁下，通过任务级质量、安全、时延和人工可用性阈值，即可先在对象抽取、分类、结构化生成等可控任务上扩大使用范围。验证时使用统一测试集和同一评分口径，避免部署位置带来的非公平比较。")
    add_text(doc, "上述假设的共同前提是：模型结论与业务动作必须分离。系统可以让模型生成事实摘要、候选关系、解释、推荐和风险说明，但不能把自然语言输出直接视为“活动已发布”或“规则已生效”。因此，项目同时关注模型能力与制度化约束能力，强调可审计的协同而不是无边界的自动化。", after=5)

    add_heading(doc, "1.1.5  研究边界与证据原则", 3)
    add_text(doc, "项目研究对象是航空营销运营中的决策辅助与流程编排，不替代航司既有的收益管理、用户画像、产品管理、渠道投放、财务预算或 OA 审批系统。上游系统仍然是主数据和业务规则的权威来源；平台负责在授权边界内对多源信息进行语义组织、推理辅助和营销闭环编排。对于尚未接入的真实系统，本文使用“后续验证”或“拟接入”表述，不将原型数据、示例对象或工程设计直接表述为已发生的生产经营事实。", after=5)
    add_text(doc, "证据原则包括四点：第一，来源可定位，任何进入知识库或本体的事实应能回到文件、接口、数据库快照或人工确认记录；第二，状态可区分，候选、正式、生效、过期、冲突和已拒绝不能混为一谈；第三，权限可校验，推理上下文仅来自当前租户和当前角色被授权的数据范围；第四，结果可复核，模型、Prompt、工具、知识与本体版本、Token、耗时、错误和人工反馈均应成为运行记录的一部分。", after=5)


def expanded_planning(doc):
    add_heading(doc, "2.1.4  研究方法与实验设计", 3)
    add_text(doc, "项目采用“工程原型构建—对照实验—场景回放—人工评审”相结合的方法。工程原型用于确保提出的语义模型、推理编排和治理规则能够真正运行；对照实验用于在保持输入条件一致的情况下比较不同模型、不同上下文组织方式或不同工具策略；场景回放用于将抽象指标置入具体航线、客群、产品与活动流程中观察；人工评审用于判断建议是否符合业务常识、规则和可操作性。四种方法相互补充，避免只依据单一自动指标或单次人工印象得出结论。", after=5)
    add_text(doc, "实验单元以“任务”而非“模型会话”定义。一个任务由问题类型、允许读取的数据对象、知识与本体版本、可调用工具、输出 Schema、人工审核规则和评价指标组成。例如，市场热点处理任务要求生成候选 MarketSignal、Route、Opportunity 及其证据；产品匹配任务要求输出 ProductPackage、适用条件与不可用原因；内容生成任务要求引用已审核的产品事实并通过渠道规格检查。这样可保证云端服务和本地自研模型面对相同业务约束。", after=5)
    experiment_rows = [
        ["实验环节", "变量控制", "主要观测", "结果解释原则"],
        ["语义上下文对照", "固定问题、模型、工具和数据范围，仅调整是否提供本体关系与证据。", "来源可定位、关系完整、事实冲突、人工核对耗时。", "判断本体语义是否改善可解释性，不以文风优劣替代事实质量。"],
        ["模型任务对照", "固定 Prompt、上下文、工具、Schema 和人工门禁，比较百炼与内置 Qwen。", "结构合法、证据完整、规则通过、时延、失败、人工修改。", "按任务给出路由建议，不将个别成功样本泛化为整体结论。"],
        ["稳健性测试", "构造瞬时异常、异常响应、超长输入、跨租户访问和未启用提供者等条件。", "重试、错误分类、拒绝行为、密钥保护、回退与运行事件。", "判断工程防护是否有效，不替代真实生产容量压测。"],
        ["场景回放", "固定业务窗口、对象关系、审核规则与归因口径，演练完整营销链。", "候选建议、审批点、执行批次、反馈对象和复盘结论。", "验证对象链是否闭合，不将演练数据当作经营增量。"],
    ]
    add_table(doc, experiment_rows, [1500, 2800, 2400, 2300], font_size=9.8)
    add_text(doc, "为降低评测偶然性，项目将同时记录自动指标和人工反馈。自动指标能够稳定衡量响应结构、规则通过、时延、Token、错误和工具调用；人工反馈能够识别营销语义是否正确、权益表述是否可承诺、解释是否足以支持决策。二者不应互相替代：自动指标通过不代表业务可用，人工喜欢的文案也不代表系统在权限、证据和安全方面合格。", after=5)

    add_heading(doc, "2.1.5  指标体系与判定阈值设计", 3)
    add_text(doc, "项目建立“准入指标—过程指标—结果指标”三层评价框架。准入指标决定候选对象、关系或模型输出能否进入人工审核，包括对象类型、证据、置信度、端点、Schema 和权限校验；过程指标用于观察系统推理是否稳定，包括模型调用次数、Token、时延、重试、失败、工具轨迹和人工修改；结果指标用于授权业务环境中的营销效果，包括送达、互动、购票、核销、辅营、投诉、增量与 ROI。三层指标分别服务于数据质量、工程质量和业务质量，避免把它们混为一个分数。", after=5)
    add_text(doc, "判定阈值采取“任务分级、逐步收紧”的方式。低风险的文本分类、字段标准化和候选关系抽取，可以先以结构合法、证据完整、人工可快速核对为门槛；中风险的机会建议、产品组合和内容候选，还需通过业务规则、事实校验、敏感词和审核门禁；高风险的预算、权益承诺、渠道触达和规则生效，无论模型质量多高都不得取消人工确认。模型路由阈值也应随任务风险等级变化，而不是以单一准确率覆盖全部业务。", after=5)
    add_text(doc, "在指标报告方式上，项目将明确区分“原型观测”“自动化测试结果”“场景演练结果”和“真实经营结果”。例如，17 项自动化稳健性测试全部通过、一次低流量端到端调用的耗时与工具轨迹，属于工程验证证据；真实的转化增量与 ROI 只有在授权渠道、真实回传、统一归因口径和对照设计完备后才可报告。该区分既保证项目结果可解释，也防止使用演示数据造成不当宣传。", after=5)

    add_heading(doc, "2.1.6  阶段性成果组织方式", 3)
    add_text(doc, "项目成果不以单一软件截图作为交付终点，而形成可复用的多层资产：在语义层，沉淀本体对象、关系、状态、证据和准入规则；在工程层，沉淀 Harness、模型适配、工具契约、运行事件和安全策略；在评测层，沉淀任务集、指标口径、对照记录和路由建议；在业务层，沉淀典型场景、审核记录、执行对象和复盘框架。各层成果都可独立检查，也可在端到端场景中组合验证。", after=5)
    add_text(doc, "对于竞赛展示，团队将以一个完整场景贯穿说明：从外部热点或经营信号进入知识与本体，到机会识别、客群快照、产品匹配、内容与活动候选，再到审批、执行回流和复盘。展示不仅说明“模型能说什么”，还说明“模型基于什么、不能做什么、何时需要人确认、如何量化运行质量”。这种组织方式与项目的研究目标一致，也便于评审从技术、业务和治理三个层面理解成果。", after=5)


def expanded_implementation(doc):
    add_heading(doc, "3.2.7  数据源契约与语义标准化细节", 3)
    add_text(doc, "多源数据要进入统一推理链，首先需要建立数据源契约。契约并不要求所有来源使用同一物理表结构，而要求每一种来源明确其业务含义、权威程度、更新频率、时间窗口、可读取字段、脱敏要求、来源定位方法和失效条件。对于经营指标，必须明确统计口径和观察窗口；对于产品规则，必须明确适用航班、资格、库存、价格、权益和有效期；对于客群信息，必须明确其为聚合统计还是可授权的细分结果；对于热点信息，必须明确来源、发布时间、相关性和人工确认状态。", after=5)
    add_text(doc, "在标准化过程中，系统将原始字段映射为营销对象的稳定属性，而不是简单复制源系统编码。以航线为例，原始数据可能分别出现出发城市、到达城市、机场三字码、航班号和日期；本体层将其组织为 Route、Flight、MetricObservation 等对象，并通过关系表达“观测发生在哪个航线/航班、适用于哪个时间窗、支持哪个机会判断”。以产品为例，原始产品名称、价格、库存和规则文本被组织为 Product、ProductPackage、BusinessRule 与 ValueProposition，使模型能够区分可销售事实与营销表达。", after=5)
    contract_rows = [
        ["对象类别", "最小语义字段", "证据与状态要求", "推理中的用途"],
        ["市场与经营信号", "来源、发布时间、时间窗、适用航线/市场、观测指标。", "保留来源位置；区分候选、确认、过期和已拒绝。", "识别 Opportunity 并解释机会依据。"],
        ["客群快照", "筛选语义、聚合规模、授权范围、排除规则、有效期。", "不暴露无关个人明细；记录生成版本和确认人。", "约束 AudienceSnapshot 的可触达范围。"],
        ["产品与规则", "产品包、适用条件、库存、资格、价格、权益、有效期。", "以权威产品规则为优先来源；过期或冲突内容不得直接使用。", "校验 ProductPackage 与内容承诺。"],
        ["活动与反馈", "目标、预算、渠道、频控、执行批次、结果口径。", "审批与执行状态分离；反馈绑定批次、渠道和时间窗。", "组织 Campaign、Feedback 与 AttributionResult。"],
    ]
    add_table(doc, contract_rows, [1500, 2700, 2700, 2100], font_size=9.8)
    add_text(doc, "语义标准化后仍须处理时间与冲突问题。平台不假设“最新文本一定正确”，而是依据来源优先级、有效期、人工确认、版本和冲突状态决定上下文是否可用。当两份规则文件给出不同结论时，模型不应自行选择更符合语言直觉的一项，而应将冲突作为风险项输出，等待业务人员确定优先来源或更新规则。对于不具备有效期或来源的内容，系统可以作为参考知识保留，但不将其作为可直接执行营销动作的事实依据。", after=5)

    add_heading(doc, "3.2.8  知识检索、证据引用与 Prompt 契约", 3)
    add_text(doc, "知识检索的目标不是向模型堆叠尽可能多的文本，而是在问题、智能域和权限范围确定后，提供足以支撑当前决策的最小证据集合。Harness 先根据问题确定可能涉及的业务对象和智能域，再读取当前租户范围内有效的知识片段、本体关系、活动状态与规则。检索结果需保留文档标识、片段定位、对象关联、版本和有效期，使后续输出可以引用“事实来自哪里”，而不是只给出一个没有来源的结论。", after=5)
    add_text(doc, "Prompt 被视为运行契约而非单纯的文案。系统提示词描述智能域职责、允许读取的对象、可调用的工具、不可跨越的权限边界、事实与建议的区分方式及输出结构要求；用户输入提供待分析的问题或业务任务；工具结果提供可核验的中间事实。模型不得把没有工具或证据支持的假设表述为已确认事实，也不得将“建议”伪装为已经执行的动作。对于活动发布、本体更新和预算决策，Prompt 需要明确要求输出待确认事项，而不是产生完成状态。", after=5)
    prompt_rows = [
        ["输出区块", "最小内容", "校验要求"],
        ["事实与证据", "已知事实、来源标识、对象关系、时间窗与有效期。", "无来源或已过期内容不得标为已确认事实。"],
        ["分析与建议", "机会解释、候选方案、适用范围、替代方案与风险说明。", "建议需区分于事实，并绑定相关对象和规则。"],
        ["工具与规则", "调用的业务函数、返回摘要、通过或失败的校验项。", "只能使用白名单工具；结果需记录在 AgentRun。"],
        ["人工确认", "高影响动作、冲突、信息缺口、需确认的业务口径。", "不得将待确认事项写为已发布、已生效或已执行。"],
    ]
    add_table(doc, prompt_rows, [1600, 3700, 3700], font_size=9.8)
    add_text(doc, "对于长问题或大量资料，系统在模型调用前执行输入边界检查。现有实现拒绝空问题和超过 12000 字符的输入，并将连接、读取、写入与连接池超时区分配置。边界检查的目的是避免无效调用、提示注入和不可控成本，而不是以截断代替业务理解。超长或复杂资料应优先经过文件解析、知识切分、候选审核和分步检索，而非一次性塞入对话上下文。", after=5)

    add_heading(doc, "3.2.9  工具调用、规则服务与状态机协同", 3)
    add_text(doc, "AI Inference 的作用是选择分析路径并组织候选结论，确定性工具负责执行可复核的业务计算与检查。工具可以包括市场信号查询、对象关系检索、产品资格校验、库存检查、客群授权与频控检查、内容长度与敏感词检查、活动状态查询和效果指标计算。每个工具均应拥有明确的输入结构、输出结构、权限范围、超时策略和错误语义；模型只能在当前智能域允许的工具集内调用，不能直接执行任意 SQL、绕过审批或写入正式业务数据。", after=5)
    add_text(doc, "状态机用于把自然语言建议转换为可管理的业务流程。以活动为例，候选方案可以处于草稿、待审核、已驳回、已批准、待执行、执行中、已完成或已暂停等状态；状态转换由规则与人工决定，而不是由模型一句“已发布”触发。以本体对象为例，候选、正式、生效、过期、冲突和已撤销具有不同可见性与可用性。状态机确保模型无法把尚未经过审核的结果误用为下游事实。", after=5)
    tool_rows = [
        ["工具/服务类别", "模型可请求的能力", "系统必须返回的约束信息"],
        ["知识与本体检索", "定位授权证据、对象、关系、版本与关联活动。", "来源、有效期、状态、权限范围和缺失说明。"],
        ["产品与客群校验", "检查资格、库存、价格、权益、授权、保护名单与频控。", "通过/失败、不可用原因、适用条件和规则依据。"],
        ["活动与内容检查", "生成候选内容、检查渠道规格、预算、审批与状态。", "敏感项、审批要求、渠道限制和下一步人工动作。"],
        ["执行与效果分析", "读取回传事件、漏斗、异常和归因候选。", "统计口径、时间窗、缺失数据、样本边界和置信提示。"],
    ]
    add_table(doc, tool_rows, [1850, 3500, 3650], font_size=9.8)
    add_text(doc, "工具调用失败不应被模型自行掩盖。系统需要区分可重试的暂时性失败、不可重试的参数或权限错误、需要人工介入的业务冲突和可降级的知识缺失。现有客户端对 429、502、503、504 及连接类异常实施最多 3 次指数退避重试；非瞬时 4xx 错误立即失败；异常信息经过脱敏后记录。此类策略保证问题可诊断，也防止模型为了给出看似完整的回答而编造不存在的工具结果。", after=5)

    add_heading(doc, "3.2.10  模型工程、性能优化与成本控制", 3)
    add_text(doc, "模型工程的核心不是单纯追求更长回答，而是使不同任务在可接受的质量、时延和成本范围内完成。平台为每次模型调用记录模型名称、请求/生成 Token、总 Token、耗时、重试次数、错误、工具调用与最终状态。这些运行数据可用于发现某类任务是否频繁陷入多轮规划、是否重复检索同一对象、是否因无效上下文导致回答冗长，也可用于比较云端百炼服务和内置 Qwen 自研模型在相同任务中的资源消耗。", after=5)
    add_text(doc, "对于复杂问题，性能优化采用分层策略：首先通过智能域选择和对象过滤缩小上下文；其次对固定规则、产品事实和已确认本体关系实施缓存与版本控制；再次对可并行的查询与校验进行调度；最后才考虑减少模型轮次或切换模型。任何优化都不得删除证据、跳过规则或取消人工门禁。尤其在涉及权益、库存和预算时，较短的推理链必须以事实与安全不受损为前提。", after=5)
    performance_rows = [
        ["优化对象", "可采取的工程措施", "需持续观测的副作用"],
        ["上下文规模", "按智能域、对象类型、有效期和权限过滤；对重复片段去重。", "是否遗漏关键证据、降低解释完整性或引入过期信息。"],
        ["工具循环", "为常用查询设置短路条件、会话级缓存和明确的终止规则。", "是否因过早终止导致未完成必要的资格或规则检查。"],
        ["模型路由", "将结构化、分类和关系抽取等任务逐步对照到内置 Qwen。", "质量波动、人工修改、失败率、回退频率和安全边界。"],
        ["运行容量", "设置租户级并发上限、调用预算告警、限流与熔断策略。", "高峰期排队时延、服务不可用和跨租户资源争用。"],
    ]
    add_table(doc, performance_rows, [1600, 3800, 3600], font_size=9.8)
    add_text(doc, "成本控制同样应当是可解释的。模型调用预算不能只按总 Token 限制，还应与任务价值、风险等级和人工审核收益结合。例如，对低风险的分类任务可优先使用通过对照门槛的本地模型；对跨对象复杂分析可暂用百炼主用链路；对需要真实发布的活动，即使模型调用成本较低，也必须保留规则和审核成本。平台的目标是用可观测的数据支持决策，而不是简单将成本压缩到最低。", after=5)

    add_heading(doc, "3.2.11  典型场景的端到端推理拆解", 3)
    add_text(doc, "以“上海—三亚国庆早鸟”场景为例，系统从机会识别开始，而不是从一句“请写一条促销文案”开始。第一步，外部目的地热度、App 搜索增长、航线供给、客座率观测和预售窗口以来源、时间窗和适用范围进入知识与本体。机会洞察智能域在读取这些已确认或待确认对象后，形成 Opportunity 候选，并说明影响航线、证据、风险和建议时机。若市场信号缺乏来源、经营数据已过期或航线关联不足，系统应返回信息缺口而非强行推荐。", after=5)
    add_text(doc, "第二步，客群洞察智能域从授权的聚合画像和行为统计中构造 AudienceSnapshot。候选口径可以包含近期搜索、比价期、未出票、家庭出行特征等条件，但必须同时附带营销授权、保护名单、频控、排除规则、客群规模和有效期。系统输出的是可复现的聚合快照而不是旅客个人名单；营销人员需要确认该快照是否符合业务口径以及是否适合当前活动窗口。", after=5)
    add_text(doc, "第三步，产品匹配智能域在已确定的航线、航班和时间窗内，组合早鸟客票、额外行李、优选座位和目的地权益等候选 ProductPackage。模型可以提出主推与替代方案，但工具必须校验库存、适用资格、价格、权益、有效期和交付条件。任何“更省心”“更优惠”等表述都需要能回到已确认的产品事实；无法满足资格或库存条件的组合必须说明不可用原因，不能被模型包装成对外承诺。", after=5)
    add_text(doc, "第四步，活动编排和内容生成智能域将已确认的机会、客群、产品和价值主张组织为 Campaign 候选，形成 App、短信或其他授权渠道的内容版本、触点计划、预算、频控和审批摘要。模型可以根据渠道规格生成不同文案，但必须保留事实引用、敏感词提示、长度校验和待审批事项。活动在规则、预算、内容与渠道审核完成前仅是候选状态，不能直接形成外发命令。", after=5)
    add_text(doc, "第五步，授权渠道返回送达、回执、点击、购票、核销、辅营购买或失败等事件后，系统将其组织为 ExecutionBatch 与 Feedback。效果分析智能域以预先定义的时间窗和归因口径连接客群、产品、内容、渠道和交易履约结果，输出 AttributionResult 与 Review 候选。若回传不完整、样本不足或口径不一致，系统应明确标示不确定性，不将相关性解释为因果增量。", after=5)
    scenario_rows = [
        ["场景环节", "本体与工具输入", "模型候选输出", "必须确认的事项"],
        ["机会形成", "热点、搜索、供给、客座率、时间窗与来源证据。", "Opportunity、机会解释、影响范围与时机。", "证据是否充分、是否进入策划。"],
        ["客群快照", "聚合画像、授权、频控、保护名单、有效期。", "AudienceSnapshot、规模、标签解释与排除条件。", "客群口径和触达边界。"],
        ["产品匹配", "产品规则、库存、价格、资格、权益与航班条件。", "ProductPackage、主推/替代方案、不可用原因。", "对外可承诺的组合与事实。"],
        ["活动与内容", "目标、预算、渠道规格、敏感词、审批规则。", "Campaign、内容版本、触点计划与风险提示。", "预算、内容、频控、审批与发布。"],
        ["反馈与复盘", "执行批次、回执、交易、履约、投诉和归因口径。", "Feedback、AttributionResult、Review 与下一轮建议。", "数据完整性、归因口径与策略调整。"],
    ]
    add_table(doc, scenario_rows, [1450, 2700, 2900, 1950], font_size=9.6)

    add_heading(doc, "3.2.12  场景评审与结果复核机制", 3)
    add_text(doc, "典型场景评审由技术与业务共同完成。技术侧检查数据是否来自授权范围、本体关系和工具调用是否符合契约、模型输出是否满足结构与安全要求、运行日志是否完整；业务侧检查机会解释是否合理、客群是否可用、产品权益是否真实、内容是否符合品牌和渠道要求、活动是否需要补充审核条件。两类评审结论均写入 HumanDecision 或对应审核记录，形成后续模型和规则优化的真实反馈。", after=5)
    add_text(doc, "复核机制强调可回放性。任意一项推荐应能复现当时使用的知识片段、本体版本、模型配置、Prompt 版本、工具输入输出、审核意见和最终状态。若后续发现来源错误、产品规则变更或归因口径调整，系统应能够定位受影响的候选、正式对象和活动版本，并支持重新处理、撤销或标注失效。可回放并不是为了追究单次模型输出，而是为了让团队持续理解“结论为何产生、何时不再适用、应如何改进”。", after=5)
    add_text(doc, "因此，项目的最终技术目标可以概括为：让 AI Inference 在航空营销中拥有可见的知识边界、可验证的运行过程、可管理的行动权限和可持续的反馈学习。云端百炼服务为前期端到端验证提供稳定支撑，本地基于 Qwen 的自研模型为后续数据可控和成本优化提供扩展方向，而营销本体与人工治理机制保证两类模型都服务于同一条可信业务链。", after=5)


def expanded_team_plan(doc):
    add_heading(doc, "3.3.3  质量保证与项目管理机制", 3)
    add_text(doc, "项目采用代码、数据、模型、文档和场景五类资产的协同管理方式。代码侧通过模块化服务、自动化测试和版本控制降低回归风险；数据侧通过来源登记、哈希、解析版本、字段白名单和候选审核保证可追溯性；模型侧通过提供者配置、Prompt 版本、Token 与运行事件记录保证可比较性；文档侧通过本体规范、测试报告和项目说明同步口径；场景侧通过审批点、演练记录和复盘结果连接技术实现与业务解释。", after=5)
    add_text(doc, "在迭代节奏上，团队先对低风险、可结构化的任务进行验证，再逐步扩展到需要多对象关联和业务判断的任务。任何新对象类型、新工具、新模型路由或新渠道接入，都应先经过权限、数据质量、输出结构、人工审核和回退策略检查。若发现提示注入、来源冲突、异常响应、跨租户访问、规则失效或业务口径不清等问题，优先记录并收敛风险，而不是为了演示完整性绕过问题。", after=5)
    qa_rows = [
        ["质量维度", "检查机制", "责任分工与留痕"],
        ["代码与接口", "自动化测试、异常重试、输入边界、模型提供者与租户隔离。", "工程负责人维护测试记录、运行日志和版本变更说明。"],
        ["知识与本体", "来源、证据、置信度、关系端点、状态、有效期与人工确认。", "语义建模负责人维护准入规则、审核结论和版本状态。"],
        ["模型与推理", "Schema、工具白名单、Token、时延、错误、回退、人工修改与采纳。", "平台与评测负责人维护任务集、对照结果和路由建议。"],
        ["场景与业务", "产品事实、授权、频控、预算、审批、渠道和归因口径复核。", "场景负责人记录评审意见、待确认事项与复盘建议。"],
    ]
    add_table(doc, qa_rows, [1600, 3700, 3700], font_size=9.8)
    add_text(doc, "通过上述机制，项目能够在持续扩展功能的同时保持研究结论的边界清晰：已实现的能力由代码、运行记录和测试验证支持；正在建设的能力由明确的任务、接口和验收条件描述；尚未获得真实授权环境验证的能力被保留为生产化路径。该做法既符合竞赛项目的工程展示需要，也符合研究型项目对问题、方法、证据和结论一致性的要求。", after=5)


def main_body(doc):
    add_heading(doc, "1  项目概况", 1)
    add_heading(doc, "1.1  背景和基础", 2)
    add_text(doc, "航空营销的决策对象并不是孤立的一条航线、一个客群标签或一段营销文案，而是由市场信号、航班与航线供给、产品资格、客群授权、预算与频控、渠道触达和结果反馈共同构成的动态业务系统。当前业务材料分布在文件、报表、规则、平台接口和运营经验中，语义口径、有效期和证据位置往往并不一致。若直接把这些材料输入大模型，模型虽然能够生成看似合理的文字，却难以说明依据来自何处，也无法保证输出满足库存、权益、频控和审批等业务约束。", after=5)
    add_text(doc, "本项目以东方航空营销运营为应用场景，研究“如何让 AI 推理在航空营销的业务语义、数据证据和责任边界内稳定运行”。项目不将大模型定位为自动发布器，而是将其定位为可观测的候选事实抽取器、受约束的业务分析器和可解释的方案生成器；任何涉及对外触达、预算、权益承诺、本体正式更新或规则生效的动作，均保留规则服务与人工确认门禁。", after=5)

    add_heading(doc, "1.1.1  立项依据与问题界定", 3)
    problem_rows = [
        ["业务链路中的断点", "传统处理方式的局限", "本项目拟解决的研究问题"],
        ["多源信息难统一", "文件、报表、接口与运营记录的字段口径、更新时间和来源定位不同。", "如何将非结构化与结构化信息转化为带证据、置信度、有效期和状态的营销业务对象。"],
        ["大模型输出难受控", "自然语言生成容易脱离产品事实、权限范围和营销规则，且过程不易回放。", "如何把检索、本体关系、工具调用、结构校验与人工门禁编排为可观测的推理链。"],
        ["营销闭环难归因", "机会、客群、产品、内容、执行和结果分散，复盘难回到可调整的策略要素。", "如何用统一业务对象连接“建议产生—执行反馈—归因复盘”，形成可验证的改进依据。"],
    ]
    add_table(doc, problem_rows, [2300, 3000, 3700])
    add_text(doc, "围绕上述问题，项目形成三个相互关联的核心研究问题：其一，如何构建能够表达航空营销对象、关系、状态与证据的领域本体，使信息可被检索、校验和追溯；其二，如何以统一 Harness 将模型调用嵌入业务函数、权限与审批约束中，使 AI Inference 的每一轮输入、工具选择、输出和失败均可观测；其三，如何在云端百炼服务与本地自研 Qwen 模型之间建立任务级评测与渐进路由机制，以实测指标而非模型名称决定模型使用范围。", after=5)

    add_heading(doc, "1.1.2  已有工作基础", 3)
    add_text(doc, "项目已完成可运行的原型平台：本地以 Docker 组织网页、API 与 PostgreSQL 服务，平台具备多租户工作区、模型提供商配置、文件接入、知识片段存储、本体对象与关系存储、营销助手及运行事件展示等基础能力。后端已实现统一 Harness，覆盖上下文加载、工具注册、模型调用、流式输出、Token 统计、失败重试与运行事件记录；前端已提供营销助手和数据处理工作台，便于业务人员在同一界面查看结果与过程。", after=5)
    add_text(doc, "在知识层方面，团队已形成航司营销业务本体 v1.1。该本体将“经营信号—营销机会—客户需求—营销目标—客群快照—产品包—策略方案—触点计划—活动—审批—执行—反馈—归因—复盘”表示为可管理的对象链，并明确候选、正式、生效、过期、冲突、已拒绝和已撤销等状态。知识库保存事实出处，本体表达事实之间的业务关系，二者共同为 AI 推理提供可引用、可校验的上下文。", after=5)
    add_text(doc, "在推理服务方面，前期暂以阿里云百炼 AgentStudio 提供的 OpenAI 兼容推理服务作为默认链路，用于验证真实模型接入、营销问答、知识检索、工具调用和人工审核门禁的端到端连通性。本文所称“内置测试模型”不是通用占位模型，而是团队基于 Qwen 构建并部署在本地的自研模型路径；它首先以受控对照方式进入同一 Harness，在质量、安全、时延与人工修改量达标后，逐步扩大其承担的领域任务比例。", after=5)
    expanded_context(doc)

    add_heading(doc, "1.2  场景和价值", 2)
    add_heading(doc, "1.2.1  面向航空营销的典型应用场景", 3)
    add_text(doc, "平台面向市场热点、航线与航班经营、聚合客群、客票及辅营产品、营销内容、活动审批、渠道执行和效果复盘等连续环节。以“上海—三亚国庆早鸟”场景为例：当目的地热度、App 搜索趋势、航线供给和预售窗口共同呈现机会信号时，机会洞察智能域生成带来源和时间窗的机会候选；客群洞察智能域基于授权范围内的聚合行为形成可复现的 AudienceSnapshot；产品匹配智能域对客票、行李、优选座位和目的地权益进行库存、资格和有效期校验；内容与活动智能域生成渠道候选版本并进入审批；执行与复盘智能域再将回传结果归因到客群、产品、内容和渠道。", after=5)
    add_text(doc, "该流程的价值不在于把营销人员替换为文本生成器，而在于降低跨系统查询、证据核对、规则检查和复盘串联的成本。业务人员可在每个候选结论中看到其来源、关联对象、模型运行轨迹、置信度和待确认事项；AI 推理的作用由“给出答案”提升为“基于证据形成可审查的候选建议”。", after=5)

    add_heading(doc, "1.2.2  技术价值与应用价值", 3)
    add_label_text(doc, "技术价值：", "提出领域本体、统一 Harness、工具化推理、输出 Schema 校验和人工门禁协同的应用型技术路线。该路线避免把 RAG、工作流或聊天接口孤立部署，而是使它们围绕航空营销的业务对象与状态机运行。")
    add_label_text(doc, "应用价值：", "将机会、客群、产品、内容、活动、执行与复盘连接为同一条可追溯链，帮助营销人员在复杂规则与多源信息环境中更快形成可审核的方案，同时为后续真实渠道接入和增量评估保留结构化基础。")
    add_label_text(doc, "治理价值：", "通过数据最小化、租户隔离、来源记录、候选准入、版本状态和责任分离，避免模型在没有业务依据或授权的情况下直接触发高影响营销动作，为航空场景下 AI 的可信应用提供可复用的工程范式。")

    add_heading(doc, "1.3  所需支持", 2)
    add_text(doc, "项目已具备原型验证所需的软件环境和工程基础。为从原型进一步走向可验证的业务闭环，仍需在数据授权、领域规则、算力与验证环境方面获得持续支持。所有数据接入将以授权、脱敏、聚合和最小必要为前提，平台不在营销工作台展示无关的旅客个人明细。", after=5)
    support_rows = [
        ["支持类别", "当前基础", "后续所需支持", "用于验证的目标"],
        ["数据与规则", "已有文件接入、知识片段、产品与营销对象存储能力。", "授权的聚合客群、产品规则、航线经营指标、渠道回传样本及口径说明。", "检验本体抽取、规则校验与归因链路。"],
        ["模型与算力", "百炼兼容推理服务已接入；本地内置 Qwen 自研模型具备受控验证入口。", "本地推理资源、隔离测试集、模型版本与任务路由配置。", "进行同条件质量、时延、成本和稳健性对照。"],
        ["业务验证", "活动、审批、执行和复盘已形成原型对象链。", "业务专家参与候选审核、规则确认与典型场景演练。", "确认输出可理解、可审计、可被运营使用。"],
        ["工程保障", "Docker、PostgreSQL、API、前端工作台与自动化测试已可用。", "持久化任务队列、独立 Worker、授权渠道和回调环境。", "验证长任务恢复、真实闭环与生产化边界。"],
    ]
    add_table(doc, support_rows, [1350, 2700, 2950, 2000])

    add_heading(doc, "2  项目规划", 1)
    add_heading(doc, "2.1  整体目标", 2)
    add_text(doc, "项目总体目标是构建面向航空营销的可信 AI 推理原型：以营销本体统一表达业务语义，以知识证据约束模型上下文，以统一 Harness 管理模型与工具运行，以人工审核和规则服务约束高影响动作，并以任务级评测支持云端百炼服务与本地自研 Qwen 模型的渐进式协同。项目验收强调“可运行、可追溯、可验证、可治理”，而非仅展示单次自然语言生成效果。", after=5)
    add_heading(doc, "2.1.1  研究内容与关键目标", 3)
    objective_rows = [
        ["研究内容", "关键目标", "可检查的系统证据"],
        ["营销本体与知识底座", "将业务资料转化为候选对象、关系、证据、置信度和状态，并经人工确认后进入正式图谱。", "知识文档/片段、本体对象/关系、来源定位、审核记录与版本状态。"],
        ["受控 AI 推理编排", "把授权上下文、智能域契约、工具函数、模型调用、结构校验和人工门禁组织为统一运行链。", "Harness 运行事件、工具轨迹、模型/Token/耗时、Schema 校验与审批记录。"],
        ["双模型任务级评测", "在相同提示、上下文、工具和业务门禁下，对百炼主用链路与本地自研 Qwen 进行对照。", "测试集、任务类型、质量指标、时延、错误、人工修改与路由决策。"],
        ["营销闭环验证", "以机会—客群—产品—活动—执行—反馈—归因为对象主线，验证建议能够被业务环节接收。", "候选方案、审批摘要、执行批次、反馈对象、归因结果和复盘建议。"],
    ]
    add_table(doc, objective_rows, [2100, 3400, 3500])
    add_heading(doc, "2.1.2  拟解决的关键技术问题", 3)
    add_text(doc, "第一，异构营销资料的语义准入问题。系统需要区分“可作为参考知识的文本”与“可进入本体的业务事实”，并对对象类型、关系端点、证据完整性、置信度和有效期实施校验，避免将泛化宣传或无法确认来源的信息写入正式图谱。第二，生成式推理与业务规则的协同问题。模型可提出分析路径和候选方案，但不能绕过权限、库存、资格、频控、预算和审批等确定性约束。第三，模型演进中的可比性问题。本地自研模型的扩展必须建立在同一任务、同一上下文和同一验收口径之上，避免把不同输入条件下的主观感受误作模型能力提升。", after=5)
    add_heading(doc, "2.1.3  预期成果与验收思路", 3)
    add_text(doc, "预期形成一套可运行的东方航空智能营销平台原型、一版可审计的航司营销本体、一组覆盖数据处理与六个营销智能域的推理运行规范、一套云端与本地模型对照评测方法，以及若干典型营销场景的端到端演示。验收时重点检查：每项建议是否可追溯到知识来源和本体关系；每次模型运行是否记录模型、Token、时延、工具和错误；本体正式更新和对外营销动作是否经过人工门禁；双模型是否能在统一评价框架下给出可比较的结果。", after=5)
    expanded_planning(doc)

    add_heading(doc, "2.2  技术创新点", 2)
    add_heading(doc, "2.2.1  以营销本体替代“标签堆叠”的推理上下文", 3)
    add_text(doc, "项目不把标签字典或文档向量检索直接等同于业务知识。营销本体以 Opportunity、AudienceSnapshot、ProductPackage、Campaign、ExecutionBatch、Feedback、AttributionResult 等对象及其关系表达从机会到复盘的完整业务主线。模型在生成建议时读取的是可定位、可校验、可关联的业务上下文，从而使“为何推荐、适用于谁、依赖哪些规则、由谁确认”能够在同一语义层中回答。", after=5)
    add_heading(doc, "2.2.2  将 AI Inference 组织为可观测、可回退的业务运行", 3)
    add_text(doc, "项目以统一 Harness 承担上下文加载、模型选择、工具调用、事件记录、响应校验、重试和错误脱敏。它使模型调用从页面中的黑箱请求变成具有开始、处理、校验、人工确认与结束状态的运行对象。对于网络抖动、瞬时服务错误或异常响应，系统记录失败原因并以受控策略重试或降级；对于无法满足结构或权限要求的输出，则阻止其进入后续业务链。", after=5)
    add_heading(doc, "2.2.3  云端百炼与本地自研 Qwen 的任务级渐进协同", 3)
    add_text(doc, "项目明确区分“当前可用性验证”与“后续模型替换”。前期由阿里云百炼 AgentStudio 的兼容服务支撑端到端功能联调；团队本地基于 Qwen 的自研模型以“内置测试模型”入口参与同条件对照。后续只将满足结构合法、证据完整、业务规则、时延和人工编辑等阈值的任务逐步扩展给内置模型，并保留按任务回退到云端服务的能力。", after=5)
    add_heading(doc, "2.2.4  把人工确认从事后干预前置为推理链组成部分", 3)
    add_text(doc, "项目将人工确认建模为 HumanDecision，并把候选、事实、建议与正式决策分层存储。模型可以提出机会、关系、方案和复盘建议，但活动发布、本体正式更新、预算审批、权益承诺和渠道触达均以人工确认和规则通过为前置条件。这一设计使系统能积累“采纳、修改、驳回”的反馈，为后续策略与模型评测提供真实监督信号。", after=5)

    add_heading(doc, "3  实施方案", 1)
    add_heading(doc, "3.1  技术可行性分析", 2)
    add_heading(doc, "3.1.1  原型架构与工程可行性", 3)
    add_text(doc, "平台采用“工作台—平台 API—统一 Harness—模型/工具/知识本体—数据存储”的分层架构。业务人员在前端提交问题、数据或活动草案；API 在当前租户和角色范围内组织上下文；Harness 调用模型、检索与业务函数；知识库与本体保留来源、关系和状态；活动、审批、执行和复盘对象用于承接业务闭环。该架构已经具备本地运行基础，后续可通过增加持久化任务队列、独立 Worker 与授权连接器扩展处理能力。", after=5)
    feasibility_rows = [
        ["技术环节", "现有实现基础", "可行性说明"],
        ["数据接入与处理", "文件接入、基础解析、知识文档和片段存储、数据处理智能体。", "可从受控文件和授权数据源开始，逐步接入接口/数据库连接器。"],
        ["知识与本体", "本体语义模型、对象关系存储、关系端点校验、人工确认和来源记录。", "可先以候选准入保障质量，再按对象类型扩展业务覆盖。"],
        ["模型与推理", "OpenAI 兼容客户端、流式响应、重试、Token 统计、Harness 事件和工具调用。", "模型服务与业务编排解耦，便于对照百炼与本地自研 Qwen。"],
        ["业务闭环", "机会、客群、产品、活动、审批、执行、反馈和复盘对象链。", "以原型数据和典型场景演练验证；真实渠道接入后扩展为生产归因。"],
    ]
    add_table(doc, feasibility_rows, [1800, 3500, 3700])
    add_heading(doc, "3.1.2  推理稳健性与结果边界", 3)
    add_text(doc, "项目已经形成针对模型调用与智能体运行的自动化稳健性测试。现有报告记录 17 项测试全部通过，覆盖 429、502、503、504 等瞬时异常的最多 3 次指数退避重试、连接与读取错误恢复、异常响应结构校验、空输入和超长输入拒绝、租户隔离、未启用提供者拒绝、密钥脱敏、数据流水线与六个智能域的治理门禁。该结论用于说明原型已建立关键工程防护，不等同于真实生产渠道的并发压测、经营效果结论或全部外部连接器验收。", after=5)
    add_text(doc, "历史低流量端到端测试中，平台通过一次真实模型调用完成上海—三亚营销机会分析，接口返回 HTTP 200，总耗时 44.32 秒，生成约 950 字符结果，运行过程记录 5 次模型调用、4 次结构化决策解析和 4 次工具调用。该观察表明“模型—Harness—工具—综合回答”链路能够运行，同时也暴露多轮规划和工具循环带来的时延问题。因此，项目将端到端时延、工具选择短路、缓存和路由策略作为后续优化对象，而不把单次演示数据包装为业务经营成效。", after=5)
    add_heading(doc, "3.1.3  风险、治理与生产化路径", 3)
    add_text(doc, "综合考虑数据、知识、推理、业务动作与效果评估风险，项目采用下表所示的分层控制策略。该表保留并重构了原版本的治理路线：它既说明当前原型能做什么，也明确哪些能力仍需在真实授权环境中验证。", after=4)
    governance_rows = [
        ["风险维度", "当前原型控制", "验证或扩展路径", "不可绕过的边界"],
        ["数据与隐私", "租户隔离、字段白名单、聚合画像、来源记录、服务端密钥管理。", "补齐数据分级、脱敏、访问审计、保留与删除机制。", "不得在营销工作台暴露无关旅客明细。"],
        ["知识与本体", "候选对象关系带证据、置信度、状态和人工确认；知识层与正式图谱分层。", "完善来源优先级、冲突仲裁、有效期、版本回滚和批量审核。", "低证据或低置信度内容不得自动成为正式事实。"],
        ["模型与推理", "模型配置、Token/耗时、重试、响应校验和 Harness 轨迹统一记录。", "建立基准集、任务路由阈值、成本监测、漂移监控和内置模型灰度。", "模型输出不得越过权限、Schema 和工具白名单。"],
        ["营销动作", "预算、资格、库存、频控、敏感词、内容事实与审批形成门禁。", "授权接入 OA、预算、渠道与异常补偿系统，完成回滚机制。", "对外发布、权益承诺和渠道触达必须人工确认。"],
        ["效果评估", "原型展示执行、反馈和复盘对象关系，指标只用于场景演示。", "建立标准归因口径、对照实验、增量评估和持续复盘。", "不得以原型看板数字替代真实经营统计。"],
    ]
    add_table(doc, governance_rows, [1300, 2600, 3000, 2100])

    add_heading(doc, "3.2  技术细节", 2)
    add_heading(doc, "3.2.1  总体技术路线", 3)
    add_text(doc, "项目以“数据进入时可追溯、推理运行时可约束、结果产生后可确认、业务反馈后可复盘”为主线，形成如下技术路线。", after=4)
    route_rows = [
        ["数据接入", "解析与标准化", "知识与本体准入"],
        ["授权文件、接口、数据库快照", "结构识别、切分、清洗、对象关系候选抽取", "证据、置信度、端点与状态校验，人工确认"],
        ["受控推理编排", "营销闭环执行", "评测与持续学习"],
        ["Harness 加载上下文，调用模型与业务工具，校验输出", "机会—客群—产品—内容—活动—审批—执行—反馈", "质量、时延、成本、人工修改、归因与路由策略更新"],
    ]
    table = add_table(doc, route_rows, [3000, 3000, 3000], font_size=10.5, header=True)
    for idx, cell in enumerate(table.rows[0].cells + table.rows[2].cells):
        set_cell_shading(cell, LIGHT_GRAY)
        for run in cell.paragraphs[0].runs:
            run.bold = True
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    add_text(doc, "图 1  航空营销可信 AI 推理技术路线", size=10, before=1, after=5, line=1.0,
             align=WD_ALIGN_PARAGRAPH.CENTER, first_indent=False, color=GRAY)
    add_heading(doc, "3.2.2  数据处理、知识库与本体准入", 3)
    add_text(doc, "数据处理首先登记数据来源、租户、提交人和时间，再按文档、规则、产品、经营指标、渠道结果等类别选择解析与处理策略。对于文档和报表，系统保留原始文件哈希、解析版本、页码/段落/表格位置；对于接口和数据库数据，系统通过只读权限、表/字段白名单、增量标识和脱敏规则控制读取范围。解析后的内容按业务语义切分为知识片段，并在抽取阶段生成候选对象、候选关系及其证据。", after=5)
    add_text(doc, "候选对象只有同时满足类型在允许范围内、具有稳定标识和标签、可指向证据、置信度达到准入要求等条件时，才可被标记为本体可准入；候选关系还需检查源端点、目标端点、关系类型和证据。无法稳定映射到业务对象的内容保留在知识层，不自动写入本体。这种“先知识保留、后本体准入”的机制避免模型把泛化文案、推测结论或重复信息扩散为正式业务事实。", after=5)
    add_heading(doc, "3.2.3  营销本体与六个智能域", 3)
    ontology_rows = [
        ["智能域", "核心本体对象", "AI Inference 的受约束输出", "人工门禁"],
        ["机会洞察", "MarketSignal、Route、Flight、MetricObservation、Opportunity", "机会候选、证据、影响范围、时间窗与建议时机。", "是否进入营销策划。"],
        ["客群洞察", "CustomerNeed、CustomerAggregate、AudienceSnapshot", "聚合客群、标签解释、可触达性、排除规则与有效期。", "客群口径、保护名单与频控。"],
        ["产品匹配", "Product、ProductPackage、ValueProposition、BusinessRule", "主推产品、替代方案、资格与不可用原因。", "库存、价格、权益和适用边界。"],
        ["活动编排", "StrategyPlan、TouchpointPlan、Campaign、ApprovalTask", "目标、预算、渠道、节奏、频控与审批材料候选。", "活动、预算与发布审批。"],
        ["内容生成", "ContentAsset、Channel、Evidence", "多渠道文案、事实引用、长度与风险提示。", "产品事实、品牌、敏感词与合规审核。"],
        ["效果分析", "ExecutionBatch、Feedback、AttributionResult、Review", "漏斗、异常解释、归因候选与下一轮建议。", "归因口径与策略更新。"],
    ]
    add_table(doc, ontology_rows, [1300, 2500, 3200, 2000], font_size=9.8)
    add_text(doc, "六个智能域共享同一 Harness、权限、知识本体与运行审计，但拥有不同的输入输出契约和人工审核节点。例如，机会洞察只能输出证据充分的 Opportunity 候选，内容生成只能使用已审核的产品事实，效果分析只能在获得授权回传和明确口径后形成归因结论。", after=5)
    add_heading(doc, "3.2.4  统一 Harness 与 AI 推理运行链", 3)
    inference_rows = [
        ["运行步骤", "处理内容", "系统记录的推理证据"],
        ["请求与权限校验", "校验登录身份、租户、角色、输入长度与模型提供者可用性。", "请求标识、租户、拒绝原因和安全事件。"],
        ["上下文加载", "读取授权知识片段、本体对象关系、活动状态、业务规则和工具白名单。", "来源、对象、版本、有效期和上下文事件。"],
        ["智能域与工具编排", "把问题映射到对应智能域，由模型在允许范围内选择检索、评分、资格、频控等工具。", "智能域契约、模型名称、工具输入输出摘要与耗时。"],
        ["结构与事实校验", "校验响应结构、引用、敏感内容、权限和确定性业务规则。", "Schema 结果、风险项、失败或降级事件。"],
        ["人工确认与结果回写", "将高影响候选送入审批，保存运行记录、证据、反馈和复盘关联。", "HumanDecision、AgentRun、Recommendation 与 Review 对象关系。"],
    ]
    add_table(doc, inference_rows, [1750, 3850, 3400])
    add_heading(doc, "3.2.5  双模型使用策略与评测设计", 3)
    add_text(doc, "前期，阿里云百炼 AgentStudio 的 OpenAI 兼容服务作为默认推理链路，重点验证模型调用、知识检索、本体查询、工具编排、流式输出和审核门禁的可用性。团队基于 Qwen 的本地自研模型通过内置测试模型入口，在不改变 Prompt 模板、知识与本体上下文、工具白名单、输出 Schema 和人工门禁的前提下，完成领域问答、对象关系抽取、分类和结构化生成等任务的对照。", after=5)
    model_rows = [
        ["比较维度", "观测指标", "用于路由的判断"],
        ["结构与事实", "响应结构合法率、证据引用完整率、关系端点合法率、业务规则通过率。", "任务输出是否达到可进入人工审核的最低质量。"],
        ["效率与成本", "端到端时延、Token 用量、重试次数、失败率、资源占用。", "同类任务是否具备可接受的性能和稳定性。"],
        ["人工可用性", "人工修改量、采纳率、驳回原因、审核耗时。", "输出是否真实降低审核和运营负担。"],
        ["安全与治理", "越权访问、敏感信息泄露、提示注入、跨租户隔离和回退成功率。", "任务是否满足扩大内置模型使用的安全门槛。"],
    ]
    add_table(doc, model_rows, [1700, 4000, 3300])
    add_text(doc, "评测遵循“先任务、后模型”的原则：任一模型都不得因名称或部署位置而天然获得更高权限。对于通过统一质量、安全、时延和人工编辑门槛的任务，可逐步提高内置 Qwen 自研模型的承担比例；当质量波动、规则失败或服务异常发生时，系统应记录原因并按策略回退到百炼主用链路。", after=5)
    add_heading(doc, "3.2.6  评价指标与典型场景验证", 3)
    evaluation_rows = [
        ["评价层级", "核心指标", "评价目的", "结果使用边界"],
        ["推理工程质量", "结构合法、重试恢复、错误、Token、时延、工具轨迹。", "确认服务可用、可观测、异常可诊断。", "不直接等同于营销效果。"],
        ["知识与本体质量", "对象抽取、关系端点、证据覆盖、置信度、冲突和过期状态。", "确认推理上下文可信且可回溯。", "低质量候选不得进入正式图谱。"],
        ["业务建议质量", "机会解释、客群合理性、产品资格、内容事实、审批结果、人工修改。", "确认建议符合航空营销规则并可被业务人员使用。", "需由业务人员审核后确认。"],
        ["营销结果质量", "送达、互动、购票、核销、辅营、投诉、增量与 ROI。", "确认授权渠道接入后的真实业务效果。", "仅以真实回传和统一归因口径计算。"],
    ]
    add_table(doc, evaluation_rows, [1550, 3150, 2750, 1550], font_size=9.8)
    add_text(doc, "典型场景以“上海—三亚国庆早鸟”为验证主线。系统先将目的地热度、搜索增长、航线供给、客座率观测和预售窗口关联为机会证据，再形成带有效期和排除规则的聚合客群快照；随后对产品包的库存、资格、权益和有效期进行校验，生成渠道内容与活动候选，待审批后才可形成执行批次。执行结果以 Feedback 和 AttributionResult 回流，用于评价客群、产品、内容和渠道的组合，而不是将模型生成文本本身视作最终成效。", after=5)
    expanded_implementation(doc)

    add_heading(doc, "3.3  计划和分工", 2)
    add_heading(doc, "3.3.1  实施计划", 3)
    plan_rows = [
        ["阶段", "主要任务", "阶段产出与核验"],
        ["第一阶段：语义底座", "完善数据接入、知识切分、候选对象关系抽取和本体准入；固化对象、关系、状态和证据规范。", "可查看来源定位、候选状态、人工确认和正式本体更新记录。"],
        ["第二阶段：受控推理", "完善 Harness、工具权限、结构校验、运行事件和六智能域输入输出契约。", "每次推理可检查上下文、模型、Token、时延、工具、错误和人工门禁。"],
        ["第三阶段：双模型评测", "构建任务集，对照百炼主用链路与本地自研 Qwen，确定任务级阈值与回退策略。", "形成质量、安全、时延、人工修改和路由建议的对照记录。"],
        ["第四阶段：闭环演示", "围绕典型航线营销场景完成机会、客群、产品、内容、审批、执行和复盘演示。", "形成可回放的场景链路、评测结果、风险说明和优化建议。"],
    ]
    add_table(doc, plan_rows, [1800, 4000, 3200])
    add_heading(doc, "3.3.2  团队分工", 3)
    role_rows = [
        ["成员", "主要职责", "对应成果"],
        ["胡于飞", "总体方案、平台工程、模型接入与推理运行链设计。", "系统架构、Harness、模型路由、端到端验证与项目整合。"],
        ["林李洋", "营销本体、数据处理、知识准入与业务流程建模。", "本体语义模型、候选审核规范、机会到复盘对象链。"],
        ["张婷婷", "场景设计、评测口径、内容与活动验证、文档与展示。", "典型场景、业务审核点、指标体系、演示材料与复盘。"],
    ]
    add_table(doc, role_rows, [1500, 4000, 3500])
    add_text(doc, "团队以“工程实现—语义建模—业务验证”协同推进。每一阶段均以可检查的对象、运行记录、测试结果或场景回放作为交付依据；对无法由当前原型直接证明的生产化结论，文档明确标注为后续验证路径，不以推测替代事实。", after=5)
    expanded_team_plan(doc)

    doc.add_page_break()
    add_heading(doc, "4  参考资料", 1)
    references = [
        "[1] 《第八届中国研究生人工智能创新大赛初赛作品提交规范》。",
        "[2] 《第八届中国研究生人工智能创新大赛项目文档模板》。",
        "[3] 《东方航空智能营销平台》项目 README 与工程说明，项目仓库，v2.7。",
        "[4] 《东方航空智能营销平台数据处理与 AI 营销全流程说明 v1.0》。",
        "[5] 《航司营销业务本体 v1.1》。",
        "[6] 《市场热点智能体与本体处理方案 v1.0》。",
        "[7] 《AI 智能体功能与鲁棒性测试报告 v1.0》。",
        "[8] services/platform-api/app/ontology/semantic_model.py，航司营销本体语义模型实现。",
        "[9] services/platform-api/app/agents/harness.py，统一智能体 Harness 实现。",
        "[10] services/platform-api/app/llm.py 及 tests/test_llm_robustness.py，模型调用、重试和安全验证实现。",
        "[11] GitHub：PLiO-LIN/CeairMarketing，项目主分支代码与提交记录。",
    ]
    for ref in references:
        add_text(doc, ref, size=10.5, before=0, after=4, line=1.25,
                 align=WD_ALIGN_PARAGRAPH.LEFT, first_indent=False)


def build():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    configure_styles(doc)
    configure_section(doc.sections[0])
    core = doc.core_properties
    core.title = "东方航空智能营销平台项目文档"
    core.subject = "第八届中国研究生人工智能创新大赛"
    core.author = "丽娃谷风"
    core.comments = "V1.5：竞赛模板章节、基金申请书式正文与扩展技术论证"
    cover(doc)
    toc(doc)
    revision_history(doc)
    main_body(doc)
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    build()
