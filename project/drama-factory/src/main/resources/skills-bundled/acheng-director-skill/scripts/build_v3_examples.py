"""Authored narrative/asset cases and original drawn keyframe references; no model calls."""
import copy
import hashlib
import json
from pathlib import Path
from build_examples import EXAMPLES, ROOT, camera, nail, segment, shot, state, write_json, prepare_fixture_bindings
from asset_plan import check_asset_plan, prepare_asset_card
from director_dispatch import plan_dispatch


def card(aid, description, kind="character", dependencies=()):
    light = "Use the stated world-space light source, keeping its direction consistent across the scene, with readable shadow planes and localized contact shadows." if kind in ("scene", "keyframe") else "Use one broad upper-left light with readable shadow planes and localized contact shadows."
    refs = [{"image": i + 1, "asset_id": dep[0], "asset_version": "v1.0", "role": dep[1],
             "subject": dep[2], "preserve": dep[3], "exclude": "unrelated pose, crop and lighting; use the target composition described below"} for i, dep in enumerate(dependencies)]
    return {"id": aid, "name": description.split(".")[0], "asset_version": "v1.0",
            "target_skill": "im2-clean-image", "source_repository": "im2-image-skills",
            "recipe": "portrait" if kind == "character" else "hard_surface", "mode": "GENERATE",
            "reference_policy": "required" if refs else "none", "references": refs,
            "transaction": {"change": "Create the single still specified in the complete prompt.", "preserve": "The stated identity, object count, geometry and material distinctions.", "rebuild": "Render the requested framing with coherent contact, shadows and visible surfaces."},
            "seven_steps": [{"step": i + 1, "content": text} for i, text in enumerate([
                description, "Use the explicitly stated visual medium.", "Keep the subject fully readable with quiet surrounding space.",
                light + " Separate matte paper, cloth, wood and metal only where each is present.",
                "Keep detail at the identity features and functional contact points; simplify distant masses.",
                "Restrict fine texture to the visible scale and keep broad surfaces calm.",
                "Avoid ghost texture, duplicated objects and unintended text."])],
            "prompt": description + " " + light + " Keep the principal silhouette and functional details clear, with broad quiet background shapes. Separate the stated materials through their surface response. Avoid ghost texture, duplicated anatomy and unintended text.",
            "generation_status": "planned", "actual_settings": None}


def asset(aid, kind, entity, purpose, deps=()):
    return {"id": aid, "kind": kind, "entity_id": entity, "version": "v1.0", "purpose": purpose,
            "depends_on": list(deps), "status": "planned"}


def create_serial():
    cast = [
        {"id": "CHAR_MEI", "name": "Meilin", "height_m": 1.68, "identity": "Original adult archive clerk",
         "prompt_description": "Meilin is a 32-year-old woman with a narrow oval face, straight black eyebrows and chin-length dark hair tucked behind her left ear. She wears a faded blue cotton jacket, cream shirt and dark straight trousers; her hands are uninjured."},
        {"id": "CHAR_BO", "name": "Bo", "height_m": 1.76, "identity": "Original adult dock mechanic",
         "prompt_description": "Bo is a 40-year-old man with a broad face, short salt-and-pepper hair and a small pale scar on his left cheek. He wears a brown canvas vest over a rolled-sleeve gray shirt and dark work trousers; his hands are uninjured."}]
    scenes = [
        {"id": "SC_ARCHIVE", "name": "潮汐档案室", "version": "v1.0", "prompt_description": "The harbor archive has a waist-high oak reading table, one frosted east window, a north shelf of cloth-bound ledgers and a west door. Soft window light falls across the table; the shelf remains in broad shadow."},
        {"id": "SC_DOCK", "name": "码头值班亭", "version": "v1.0", "prompt_description": "The dock watch hut has a fixed timber counter, an east window overlooking the tide gauge, a west door and a brass bell mounted on its north post. A waist-high manual-bypass cabinet below the east window bears an unbroken paper seal. Broad overcast daylight enters from the east; wet boards remain matte except at small puddles."}]
    # Twelve complete dramatic beats spanning three episodes. Dialogue is original.
    authored = [
        (0,"调查","Meilin compares two tide entries and places a narrow paper marker beside their matching ink notches, leaving the marks visible and both original ledgers on the table.","两次高潮，怎么会连笔误都一样？","找出重复记录","官印使记录看起来无误","先标记疑点而不宣判","必须暂缓归档","她发现记录可能不是独立测量"),
        (1,"工务","Bo points to the hut's sealed manual bypass, then opens his empty hands toward the tide gauge outside.","封条是真的，水位也是真的。","证明仪表仍工作","完整封条阻止开柜","先保留现场而不破封","错过最方便的检查方法","真正的封条与异常读数可以同时存在"),
        (0,"互信","Meilin turns the comparison page toward Bo and leaves the two originals beside each other, allowing him to mark a separate column.","这一次，你来记第二列。","取得独立复核","她习惯独自控制证据","让另一人保留独立记录","放弃单一解释权","双方约定分开记录再交叉核对"),
        (1,"旧案","Bo taps the bell mount and compares its wear mark with an old tide sheet laid on the counter.","那晚不是钟停了，是交班表晚了一格。","重看旧事故","旧表被当作可靠时间基准","公开自己的当班失误","承担重新调查的责任","旧事故中的钟声可能比表格可靠"),
        (0,"制度","Meilin lays a signed closure notice beside the discrepant ledgers and keeps her pen above its unsigned receipt.","签收不等于认可，我把异议附上。","保存复核机会","封存程序要求立刻签收","签收同时附书面异议","自己的名字进入责任链","合法程序留下了异议的可追溯入口"),
        (1,"外部","Bo aligns a shipping manifest with the tide sheet without moving either page out of the hut.","船是按钟走的，不是按我们的表走的。","寻找独立时间来源","船期资料只证明离港时点","把航运钟点与本地测量分开","不能再用单一表格解释全部证据","外部航运记录能验证时间差"),
        (0,"互信","Meilin removes her earlier annotation from the margin and writes a narrower observation beneath it while Bo watches.","我能证明抄过，还不能证明是谁。","收紧指控范围","她先前把怀疑当作结论","主动撤回无证据的姓名指控","失去立即定责的快感","两人区分造假事实与责任人身份"),
        (1,"防汛","Bo places a sandbag against the west threshold while Meilin keeps the tide sheet dry on the counter.","先把门槛垫住，证据不能替我们挡水。","保住现场与人员","涨潮先于调查结论到来","先保护门槛而不追赶传话者","失去一次追问机会","保存证据与应急行动共同推进"),
        (0,"调查","Meilin aligns the ink notches on both originals and opens Bo's independently written column beside them.","两张官表是一份底稿，第二列不是。","证明记录缺乏独立性","相同官印曾被当作相互佐证","公布原件与独立复核的对应","档案室必须承认程序漏洞","重复笔误兑现为记录同源的物证"),
        (1,"旧案","Bo points first to the shipping departure time, then to the tide gauge and the worn bell bracket.","三处对得上，错的是交班时刻。","还原旧事故时序","此前各方使用不同时间基准","接受可被外部证实的重建","承认自己的疏漏仍有责任","钟、航运记录与仪表共同纠正旧案误读"),
        (0,"制度","Meilin places the signed objection next to both originals and leaves the receipt line visible rather than covering it with the final report.","更正记录，不撤掉异议。","防止更正抹去争议","结案手续倾向只留最终结论","同时保存原件、更正和异议","以后仍可追问本次调查","纠错过程获得持续可追溯性"),
        (1,"主题","Meilin and Bo stand on opposite sides of the counter, each checking one column before both step back from the dry tide sheet.","下一班，也留两个人的记录。","建立新的交班方法","日常工作偏好最快签字","保留独立复核与共同签认","接受更慢但可纠正的流程","互信表现为允许彼此留下不同证据")]
    thread_names = ["调查","工务","互信","旧案","制度","外部","防汛","主题"]
    chinese_actions = [
        "梅林把两份潮汐原件并排摊开，指尖停在相同的墨迹缺口上，用纸签标出位置。",
        "柏先指向完整的手动旁路封条，再摊开空手，示意窗外仍在工作的水位尺。",
        "梅林把比对页转向柏，让出桌面另一侧；柏在独立的空白列中落笔，两份原件留在原处。",
        "柏轻敲钟架磨损处，把旧潮汐表压平在柜台上，以指尖对照原来的交班时刻。",
        "梅林把签署过的封存通知放到原件旁，笔尖悬在尚未签收的一栏上，然后补入异议。",
        "柏将航运单与潮汐表边缘对齐，让离港时点和本地测量时点分别保持可见。",
        "梅林划去页边先前写下的姓名，在下方补上范围更窄的观察，柏没有替她落笔。",
        "柏从柜台下搬出沙袋，抵住西侧门槛；梅林把潮汐表留在干燥的柜台上。",
        "梅林让两份原件的墨迹缺口对齐，再摊开柏独立记录的第二列，三者同时留在桌面。",
        "柏依次指向航运离港时刻、窗外水位尺和磨损钟架，手指最后停在旧表的交班格。",
        "梅林把签过字的异议放在原件旁，保留签收栏的可见位置，没有用结案报告盖住它。",
        "两人分站柜台两侧，各复核一列记录，再同时后退半步，让干燥的潮汐表留在两人之间。"]
    threads = [{"id": f"THREAD_{i+1:02d}", "question": f"{name}线如何改变调查的方法与代价", "function": "relationship" if name=="互信" else "thematic" if name=="主题" else "world" if name in ("制度","工务","外部") else "external", "visibility": "covert" if name=="旧案" else "overt"} for i,name in enumerate(thread_names)]
    beat_rows, script_rows, shots, segments = [], [], [], []
    for i,(scene_index,thread,visual,dialogue,goal,obstacle,choice,cost,result) in enumerate(authored):
        bid, sid = f"BEAT_{i+1:02d}", f"SERIAL_SHOT_{i+1:02d}"
        sc = scenes[scene_index]
        start, end = i*360, (i+1)*360
        poses = [nail("CHAR_MEI",0.33,"toward screen right"),nail("CHAR_BO",0.7,"toward screen left")]
        for pose in poses:
            pose.update(weapon_hand="empty hands except when touching the described paper",weapon_direction="no weapon present")
        sh = shot(sid,start,end,"Meilin stands on the left and Bo on the right, facing each other across the shared work surface. "+visual,camera("103",50,"The camera holds a static medium two-shot from the south side, keeping both faces, hands and the document surface readable.","stationary south-side observation"),poses)
        sh["camera"].update(movement="static",adaptation="composition-only reference")
        sh.update(scene_id=sc["id"],story_beat_ids=[bid],required_assets=["ART_MEI","ART_BO", "ART_ARCHIVE" if scene_index==0 else "ART_DOCK","ART_LEDGER" if scene_index==0 else "ART_TIDE"],required_prop_ids=["PROP_LEDGER" if scene_index==0 else "PROP_TIDE"],state_description="The original papers remain flat on the table or counter in their stated room; neither person carries them away. Both people's clothing is dry above the waist and neither has an injury.")
        sh["state_description"] = ("Two cloth-bound tide ledgers lie open on the oak table, with two cream paper markers and a short wooden pencil nearby." if scene_index==0 else "A tide sheet and a separate shipping manifest lie flat side by side on the timber counter.") + " Neither person carries the papers away. Both people's clothing is dry above the waist and neither has an injury."
        if i in (0,8):
            sh["camera"]=camera("001",65,"The camera begins with both people and the tabletop in view, then slowly advances forty centimeters and tilts down to end on the two matching ink notches and nearby hands. The faces leave the upper edge naturally without a cut.","slow south-side forward push with a gradual downward tilt toward the open ledgers")
        if i==7:
            sh["camera"]=camera("102",35,"The camera holds a wide south-side view including the west threshold, the counter and both full figures, so the lifted sandbag remains visible until it touches the door sill.","stationary wide south-side observation")
            sh["camera"].update(movement="static",adaptation="composition-only")
        name = "Bo" if visual.startswith("Bo") else "Meilin"
        sh["dialogues"]=[{"speaker_id":"S1" if name=="Meilin" else "S2","speaker_name":name,"language":"Chinese","text":dialogue,"delivery":"speaking evenly with a low resonant voice and short declarative phrases" if name=="Bo" else "speaking precisely in a clear mid-pitched voice, pausing before the final clause","start":144,"end":320,"voiceover":False}]
        foley = "Canvas scrapes against the boards as Bo lifts the sandbag; it lands against the sill with a muted thud." if i==7 else "A dull brass tap follows Bo's fingertip touching the bell mount." if i==3 else "Cloth shifts with the pointing gesture while wind brushes the outside wall." if i==1 else "Paper edges rasp softly as a fingertip follows the visible marks; cloth moves with each small reach."
        sh["audio"]={"foley":[foley],"low_frequency_hz":None,"no_low_frequency_reason":"No designed bass event in this quiet investigation."}
        shots.append(sh)
        segments.append(segment(f"SERIAL_SEG_{i+1:02d}",[sh],"Live-action coastal mystery with quiet natural light, readable paper surfaces and restrained gestures.","Distant harbor wind and quiet breathing continue beneath small wooden creaks. "+foley))
        b={"id":bid,"episode":f"EP_{i//4+1:02d}","story_time":f"调查第{i//4+1}日，第{i%4+1}场","scene_id":sc["id"],"characters":[c["id"] for c in cast],"primary_thread":threads[thread_names.index(thread)]["id"],"secondary_threads":[],"depends_on":[f"BEAT_{i:02d}"] if i else [],"goal":goal,"obstacle":obstacle,"choice":choice,"cost":cost,"result":result,"requires_knowledge":[]}
        if i==0: b["entry_cause"]="例行归档时两份应独立测量的记录出现同样笔误"
        if i>=8: b["requires_knowledge"]=[{"holder":"CHAR_MEI","fact_id":"FACT_COPY","state":"knows"}]
        beat_rows.append(b)
        script_rows.append({"id":f"SCENE_{i+1:02d}","scene_id":sc["id"],"scene_name":sc["name"],"thread":b["primary_thread"],"beat_ids":[bid],"text":f"第{i//4+1}集·第{i%4+1}场｜{sc['name']}｜日·内\n△ {chinese_actions[i]}\n{'柏' if name=='Bo' else '梅林'}：{dialogue}\n△ 对方让说话者把手中动作完成，再将视线移回同一份证据。原件留在原处，两人没有离开这个场所。"})
    events=[{"id":"KNOW_01","holder":"CHAR_MEI","fact_id":"FACT_COPY","before":"unknown","state":"suspects","after_beat_id":"BEAT_01","evidence":"两份记录出现相同笔误"},
            {"id":"KNOW_02","holder":"CHAR_MEI","fact_id":"FACT_COPY","before":"suspects","state":"knows","after_beat_id":"BEAT_07","evidence":"原件笔误与独立复核已能区分抄录事实和责任人身份"},
            {"id":"KNOW_03","holder":"AUDIENCE","fact_id":"FACT_COPY","before":"suspects","state":"knows","after_beat_id":"BEAT_09","evidence":"镜头同框展示两原件和独立第二列"}]
    story={"contract_version":"3.0","synopsis":"三集各一分钟的沿海调查样例。档案员梅林起初把制度认证当作真相；工务员柏保留旧案责任。两人用不同来源交叉核对潮汐记录，区分抄录事实与责任人身份，最终保留异议而非用新结论覆盖旧证据。八条线路在12个完整场次内交汇；这是跨集机制示例，不声称已制作长篇成片。","threads":threads,"beats":beat_rows,"facts":[{"id":"FACT_COPY","truth":"两份官表来自同一份底稿，不能作为两次独立测量"}],"initial_knowledge":[{"holder":"AUDIENCE","fact_id":"FACT_COPY","state":"suspects","evidence":"开场同时看见两个相同笔误"}],"knowledge_events":events,
           "setups":[{"id":"SETUP_INK","setup_beat":"BEAT_01","surface_reading":"重复笔误似乎只是抄写习惯","reinforcement_beats":["BEAT_04","BEAT_07"],"payoff_beat":"BEAT_09","effect":"让主角公开区分认证与独立证据"},{"id":"SETUP_BELL","setup_beat":"BEAT_02","surface_reading":"封条完整意味着设备没有问题","reinforcement_beats":["BEAT_04","BEAT_06"],"payoff_beat":"BEAT_10","effect":"多个独立时钟重写旧事故的责任解释"}],
           "character_arcs":[{"id":"ARC_MEI","character_id":"CHAR_MEI","kind":"positive","want":"完成无争议的归档","need":"允许独立复核和可记录的异议","belief":"认证完整就意味着结论可信","voice":"短句精确、先界定证据再下结论","relationship_debt":"曾独断否定柏的旧案解释","evidence":[{"beat_id":"BEAT_03","choice":"主动让另一人填写独立第二列"},{"beat_id":"BEAT_07","choice":"撤回缺乏证据的指控"},{"beat_id":"BEAT_12","choice":"把相互校验留给下一班"}]},{"id":"ARC_BO","character_id":"CHAR_BO","kind":"flat","want":"纠正旧案的时间误读","need":"承担自己的疏漏而不吞下全部错误","belief":"证据可以不同，责任不能推给一张纸","voice":"具体物件和操作动词，少用抽象口号","relationship_debt":"因旧事故不愿再把记录交给梅林","evidence":[{"beat_id":"BEAT_04","choice":"公开自己的当班失误"},{"beat_id":"BEAT_10","choice":"接受独立来源能证明的责任重建"}]}],"locked_dialogue":[{"scene_id":"SCENE_07","text":"我能证明抄过，还不能证明是谁。"}]}
    story["relationships"]=[{"id":"REL_MEI_BO","characters":["CHAR_MEI","CHAR_BO"],"initial":"保持礼貌但不肯共享解释权","events":[{"beat_id":"BEAT_03","before":"保持礼貌但不肯共享解释权","after":"愿意保留各自独立记录","evidence":"梅林让出第二列，柏接受独立复核"},{"beat_id":"BEAT_07","before":"愿意保留各自独立记录","after":"允许对方撤回错误而不取消其发言权","evidence":"梅林缩小指控范围，柏不替她写结论"},{"beat_id":"BEAT_12","before":"允许对方撤回错误而不取消其发言权","after":"把互相校验作为持续合作方式","evidence":"两人分别复核并共同让出记录空间"}]}]
    initial={"characters":{c["id"]:{"ammo":0,"trauma_phase":None} for c in cast},"scenes":{s["id"]:0 for s in scenes},"props":{"PROP_LEDGER":"SC_ARCHIVE","PROP_TIDE":"SC_DOCK","PROP_NOTICE":"SC_ARCHIVE","PROP_SANDBAG":"SC_DOCK","PROP_STATIONERY":"SC_ARCHIVE"}}
    p={"version":"2.0","delivery_scope":"full_production","project_id":"SERIAL_TIDE_ARCHIVE","fps_num":24,"fps_den":1,"production_total_duration":180,"generation_clip_min":4,"generation_clip_limit":15,"character_registry":cast,"scene_registry":scenes,"shots":shots,"segments":segments,"ledger":state(initial,shots,[]),"story":story,"script_scenes":script_rows,"asset_plan":[],"asset_cards":[],"style_policy":"legacy_unlocked","style_policy_reason":"Historical v3 serial fixture predates STYLE_MOTHER; cross-asset style consistency is not guaranteed.","prompt_detail_policy":{"profile":"legacy_fixture"}}
    descriptions=[("ART_MEI","character","CHAR_MEI","Create a neutral full-body live-action character reference. "+cast[0]["prompt_description"]), ("ART_BO","character","CHAR_BO","Create a neutral full-body live-action character reference. "+cast[1]["prompt_description"]), ("ART_ARCHIVE","scene","SC_ARCHIVE","Create an unoccupied live-action environment reference. "+scenes[0]["prompt_description"]), ("ART_DOCK","scene","SC_DOCK","Create an unoccupied live-action environment reference. "+scenes[1]["prompt_description"]), ("ART_LEDGER","prop","PROP_LEDGER","Create a live-action reference of two cloth-bound tide ledgers lying open side by side, with cream paper and matching tiny ink notches in their right margins. Other writing is indistinct, with no invented readable text."), ("ART_TIDE","prop","PROP_TIDE","Create a live-action reference of a cream tide sheet and a separate shipping manifest lying flat side by side on aged timber. Show neat columns and small ink marks without invented legible writing.")]
    for aid,kind,entity,desc in descriptions:
        p["asset_plan"].append(asset(aid,kind,entity,desc))
        p["asset_cards"].append(card(aid,desc,kind))
    extras=[("ART_NOTICE","PROP_NOTICE","Create a live-action prop reference of one cream closure notice and a separate written objection on an oak tabletop. Use visible ruled receipt fields and a small blue signature mark, with other writing indistinct and no invented legible text.",[4,10]),
            ("ART_SANDBAG","PROP_SANDBAG","Create a live-action prop reference of one squat tan canvas sandbag tied with dark cord. Its bottom flattens under its weight and its seams remain visible; the canvas has a few broad folds and no printed writing.",[7,9,11]),
            ("ART_STATIONERY","PROP_STATIONERY","Create a live-action prop reference of one short wooden pencil, two narrow cream paper markers and one loose comparison sheet with two ruled columns. Keep the paper matte and the graphite tip dark; marks are indistinct without invented readable words.",[0,2,6,8,10])]
    for aid,entity,desc,consumers in extras:
        p["asset_plan"].append(asset(aid,"prop",entity,desc)); p["asset_cards"].append(card(aid,desc,"prop"))
        for index in consumers:
            shots[index]["required_assets"].append(aid); shots[index]["required_prop_ids"].append(entity)
    for index,s in enumerate(shots):
        if s["scene_id"]=="SC_DOCK":
            s["state_description"] += " A single tan sandbag rests beneath the counter." if index<=7 else " A single tan sandbag remains pressed against the west threshold."
    for n in (0,4,8):
        aid=f"ART_KEYFRAME_{n+1:02d}"
        deps=[("ART_MEI","identity","Meilin the adult archive clerk","her face, hair, adult proportions and blue cotton jacket"),("ART_BO","identity","Bo the adult dock mechanic","his face, cheek scar and brown canvas vest"),("ART_ARCHIVE","scene","the archive room","the oak table, east window, north shelf and west door"),("ART_LEDGER","composition","the two original ledgers","the two cloth bindings and matching ink notches")]
        extra = ""
        if n==0:
            deps.append(("ART_STATIONERY","composition","the pencil and paper markers","the short wooden pencil and narrow cream paper markers")); extra=" A short wooden pencil and two narrow cream paper markers lie beside the original ledgers."
        elif n==4:
            deps.append(("ART_NOTICE","composition","the closure notice and objection","their paper format and ruled receipt fields")); extra=" A closure notice and separate written objection lie beside the ledgers, with the receipt line visible."
        elif n==8:
            deps.append(("ART_STATIONERY","composition","the independent comparison sheet","its two ruled columns and short wooden pencil")); extra=" A separate two-column comparison sheet lies beside both original ledgers, its edge aligned with them."
        p["asset_plan"].append(asset(aid,"keyframe",shots[n]["id"],"本集开场的档案室单一关键帧",[x[0] for x in deps]))
        p["asset_cards"].append(card(aid,"Create one live-action medium two-shot before any gesture begins. "+" ".join(c["prompt_description"] for c in cast)+" "+scenes[0]["prompt_description"]+" Meilin stands left and Bo right, both looking down at two open ledgers lying flat between them. Their hands rest separately on the table edge."+extra,"keyframe",deps))
        shots[n]["required_assets"].append(aid)
    names={"ART_MEI":"梅林·中性全身身份基准","ART_BO":"柏·中性全身身份基准","ART_ARCHIVE":"潮汐档案室·空间母图","ART_DOCK":"码头值班亭·空间母图","ART_LEDGER":"两份潮汐原件·道具基准","ART_TIDE":"潮汐表与航运单·道具基准","ART_NOTICE":"封存通知与异议·道具基准","ART_SANDBAG":"门槛沙袋·道具基准","ART_STATIONERY":"铅笔纸签与独立比对页","ART_KEYFRAME_01":"第一集开场·原件对照","ART_KEYFRAME_05":"第二集开场·保留异议","ART_KEYFRAME_09":"第三集开场·独立佐证"}
    for item in p["asset_cards"]: item["name"]=names[item["id"]]
    p["asset_cards"] = [prepare_asset_card(item, p) for item in p["asset_cards"]]
    return prepare_fixture_bindings(p)


def draw_crane(path, x, wings=False):
    from PIL import Image, ImageDraw
    im=Image.new("RGB",(960,540),(237,233,220)); d=ImageDraw.Draw(im)
    d.polygon([(0,385),(960,370),(960,540),(0,540)],fill=(182,191,186))
    d.polygon([(50,360),(910,335),(910,365),(50,390)],fill=(78,82,76))
    for px in (145,810): d.line([(px,365),(px+8,488)],fill=(69,73,67),width=12)
    d.line([(60,279),(905,257)],fill=(100,108,99),width=5)
    d.line([(105,282),(105,363)],fill=(92,100,92),width=6)
    d.line([(865,260),(865,338)],fill=(92,100,92),width=6)
    y=int(360-(x-50)*25/860)
    d.polygon([(x-45,y-24),(x+30,y-32),(x+53,y-83),(x+23,y-67),(x+10,y-41),(x-25,y-93)],fill=(247,244,232),outline=(38,45,42),width=3)
    d.line([(x-45,y-24),(x+10,y-41),(x-25,y-93)],fill=(54,62,56),width=2)
    d.polygon([(x+23,y-67),(x+53,y-83),(x+73,y-66)],fill=(241,237,223),outline=(38,45,42),width=2)
    d.line([(x-15,y-27),(x-18,y),(x-4,y)],fill=(38,45,42),width=3)
    d.line([(x+4,y-31),(x+11,y-1),(x+23,y-1)],fill=(38,45,42),width=3)
    if wings: d.polygon([(x-6,y-43),(x-65,y-115),(x+10,y-63)],fill=(245,242,232),outline=(38,45,42),width=3)
    d.ellipse((x+44,y-78,x+48,y-74),fill=(38,45,42))
    path.parent.mkdir(parents=True,exist_ok=True); im.save(path)


def create_ink():
    desc="A small cream folded-paper crane has a triangular body, a long folded neck, a pointed beak, one black ink eye and two thin black folded legs. Its broad paper surfaces stay quiet, with a few dark fold lines."
    environment="A narrow dark wooden footbridge crosses pale green-gray water. Two supports descend below it, a thin rear rail slopes toward the right, and the warm paper background remains empty."
    paths=["media/ink-opening.png","media/ink-middle.png","media/ink-right.png","media/ink-end.png"]
    for path,x,wing in zip(paths,(210,470,720,775),(False,False,False,True)):
        draw_crane(EXAMPLES/path,x,wing)
    cast=[{"id":"CHAR_CRANE","name":"Paper crane","height_m":0.12,"identity":"Original folded-paper bird design","prompt_description":desc}]
    sc={"id":"SC_BRIDGE","name":"墨桥","version":"v1.0","prompt_description":environment}
    visuals=["The shot begins exactly from <Picture 1>, with the crane standing on the left part of the bridge and facing right. The crane makes three measured forward steps, lifting one folded foot at a time, then settles near the middle. Its body rocks lightly while the bridge and viewpoint stay fixed.",
             "The shot begins from Picture 1 with the crane standing near the middle of the bridge, facing right. It lowers its triangular body, takes two short steps and one small hop toward the right support, landing with both feet on the deck. It gradually settles into the exact pose and location of Picture 2 at the final moment.",
             "The crane begins on the right side of the bridge, its wings folded and feet planted. It takes one short step farther right, stops, and slowly unfolds its near paper wing while keeping its feet on the wood. The last moment converges to the exact crane pose, open wing, bridge framing and quiet background in <Picture 1>."]
    shots=[]; segs=[]
    for i,visual in enumerate(visuals):
        s=shot(f"INK_SHOT_{i+1}",i*288,(i+1)*288,visual,camera("102",50,"The camera stays completely still in a wide side view; the whole crane and both bridge supports remain visible.","stationary side view"),[{"id":"CHAR_CRANE","position":[(210,470,720)[i]/960,0.58],"facing":"screen right","gaze":"toward the bridge ahead","weapon_hand":"no held object","weapon_direction":"no weapon present"}])
        s.update(scene_id="SC_BRIDGE",state_description="The bridge is intact, the water is calm and the folded-paper crane is dry; no damage or carried object is present.")
        s["camera"].update(movement="static",adaptation="composition-only")
        s["audio"]={"foley":["Dry paper makes a quiet crease sound as each folded limb moves; the footfalls touch wood lightly."],"low_frequency_hz":None,"no_low_frequency_reason":"Small paper movement needs no bass accent."}
        mode=("I2VA","FL2VA","L2VA")[i]
        seg=segment(f"INK_SEG_{i+1}",[s],"Two-dimensional ink-and-paper animation matches the supplied cream paper, dark folded contours, quiet background and muted water.","Soft paper creaks and light wooden taps accompany the visible movement, with faint water below the bridge.",mode)
        refpaths=([paths[0]],[paths[1],paths[2]],[paths[3]])[i]
        seg["references"]=[{"label":f"<Picture {j+1}>","file":path,"role":"actual final target frame" if mode=="L2VA" or j==1 else "actual opening target frame"} for j,path in enumerate(refpaths)]
        shots.append(s); segs.append(seg)
    initial={"characters":{"CHAR_CRANE":{"ammo":0,"trauma_phase":None}},"scenes":{"SC_BRIDGE":0},"props":{}}
    p={"version":"2.0","delivery_scope":"prompt_only","project_id":"INK_PAPER_CROSSING","fps_num":24,"fps_den":1,"production_total_duration":36,"generation_clip_min":4,"generation_clip_limit":15,"character_registry":cast,"scene_registry":[sc],"shots":shots,"segments":segs,"ledger":state(initial,shots,[]),"prompt_detail_policy":{"profile":"legacy_fixture"}}
    p["asset_cards"]=[card("INK_CHARACTER","Create a neutral side-view asset in two-dimensional ink-and-paper animation. "+desc+" The crane stands with both feet visible against warm empty paper; its wings remain folded.")]
    p["asset_cards"][0]["recipe"]="ink"
    return p


def add_handoff(p):
    if p.get("expression_handoff"):
        return
    beats=[]
    for i,s in enumerate(p["shots"]):
        old=s["performance"]; cid=p["character_registry"][i]["id"]
        source={"id":old["beat_id"],"source_anchor":f"维修室正文第{i+1}个表演节拍","character":cid,"timing":"先观察、再克制、最后按原文说话","trigger":"对方留出接收钥匙的空掌" if i==0 else "对方承认错误并交出钥匙","state_in":"保留警觉与原有责任","displayed_state":"保持可交谈的克制姿态","leakage":"目光或呼吸短暂偏离稳定节奏","control_action":"降低动作幅度并维持对方面前的空间","residual":"对话结束后手和视线保持新的关系","continuity_out":"保留已发生的钥匙交接和右腕伤势","intensity":2,"visible_cues":[t["cue"] for t in old["tracks"].values()],"visibility":"中近景能同时看到眼睛、肩线和手","exclusions":["不得增加台词或让受伤右腕承担动作"],"prompt_ready_zh":"沿用已确认对白，以可见手势和视线承接钥匙交接。","confidence":1.0}
        beats.append(source)
        s["performance"]={"beat_id":old["beat_id"],"source_beat_id":old["beat_id"],"source_anchor":source["source_anchor"],"selected_phase":"control_action","visibility_result":"visible","visibility_evidence":"The medium-close two-shot includes eyes, shoulders and the shared desk plane.","continuity_in":"Both people retain their preceding posture and the right wrist stays supported.","continuity_out":"The existing key transfer and wrist limitation remain in force.","events":[{"phase":phase,"start":t["start"],"end":t["end"],"cue":t["cue"]} for phase,t in zip(("displayed_state","leakage","control_action","residual","continuity_out"),old["tracks"].values())],"exclusion_controls":["Lu's bandaged right wrist remains supported on the desk throughout the exchange."]}
        if old.get("acting_design"):
            s["performance"]["acting_design"] = old["acting_design"]
    p["expression_handoff"]={"version":"1.0","source_locked":True,"beats":beats,"unresolved":[]}


def render(p,path,title):
    lines=[f"# {title}","","状态：完整制作设计与提示词；未调用影视生成模型。","",f"总时长：{p['production_total_duration']}秒。","","## 剧本与镜头","",p.get("story",{}).get("synopsis","程序绘制的完整单帧参考用于I2VA/FL2VA/L2VA；它们不是AI生成样片，也不是16宫格代替首尾帧。")]
    for scene in p.get("script_scenes",[]): lines.extend(["",scene["text"]])
    for s in p["shots"]: lines.extend(["",f"### {s['id']}","",s["visual"],"",s["state_description"]])
    folder=path.name.split("-",1)[1].split(".",1)[0]
    lines.extend(["","## 可使用文件","",f"[制作数据]({path.name}) · [H3正文与上传清单](compiled/{folder}/UPLOAD.md) · [图像正文与制作顺序](compiled/images/{folder}/UPLOAD.md)","","结构验收不会代替实际画面、表演和声音验收。"])
    path.with_suffix(".md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def build():
    drama_path=EXAMPLES/"02-drama.production.json"
    drama=json.loads(drama_path.read_text(encoding="utf-8")); add_handoff(drama); write_json(drama_path,drama)
    from build_examples import render_card
    render_card(drama,"02-dramatic-micro-acting-h3.md","文戏对峙｜完整表演交接",drama_path.name)
    for factory,name,title in [(create_serial,"04-serial","潮汐档案｜三集八线与全资产依赖"),(create_ink,"05-ink","墨桥纸鹤｜非写实动作与三种关键帧模式")]:
        p=factory(); path=EXAMPLES/(name+".production.json"); write_json(path,p); render(p,path,title)
        if name=="04-serial":
            write_json(ROOT/"templates/script-stage.json",{key:p[key] for key in ("production_total_duration","character_registry","scene_registry","story","script_scenes")})
            write_json(ROOT/"templates/dispatch-request.json",{"request_id":"DIRECTOR_REQUEST_01","stage":"full","features":[],"completed_modules":[],"shot_ids":[s["id"] for s in p["shots"]],"frozen_paths":["/production_total_duration"]})
            write_json(EXAMPLES/"04-serial.asset-plan.json",check_asset_plan(p,EXAMPLES))
            write_json(EXAMPLES/"04-serial.dispatch.json",plan_dispatch(p,json.loads((ROOT/"templates/dispatch-request.json").read_text(encoding="utf-8"))))
    print("Built cross-episode narrative, asset dependency and ink keyframe examples; enriched drama handoff")


if __name__=="__main__": build()
