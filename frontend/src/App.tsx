import { FormEvent, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type StatKey = "critical_strike" | "haste" | "mastery" | "versatility";
type Stats = Record<StatKey, number>;
type Spec = { key:string; class_key:string; spec_key:string; class_name_zh_cn:string; spec_name_zh_cn:string; role:string };
type Source = { source_type:string; instance_name_zh_cn:string|null; encounter_name_zh_cn:string|null };
type Item = {
  item_id:number; name_zh_cn:string; name_en:string; icon_url:string|null;
  slot_key:string; display_slot_key?:string; item_level:number; stats:Stats; sources:Source[];
  weapon_type?:string|null; can_equip_off_hand?:boolean;
  has_special_effect:boolean; is_crafted:boolean; catalyst_eligible:boolean;
  customizable_secondaries?:boolean; secondary_stat_choices?:StatKey[]; customizable_secondary_amounts?:number[];
  wowhead_url:string; wowhead_data:string; catalyst_tier_item_id?:number|null;
  selected_crafted_secondary_stats?:Partial<Stats>;
  current_sockets?:number; maximum_user_selected_sockets?:number;
};
type Gem = { id:number; name_zh_cn:string; icon:string; category:string };
type EquipmentState = { item_id:number; item_level:number; gems?:number[]; crafted_secondary_stats?:Partial<Stats>; catalyst_tier_item_id?:number|null; equipped_slot?:"weapon"|"off_hand"|null };
type Objective = { rule:string; weights?:Partial<Stats>; stat?:StatKey; target?:number; minimum?:number; maximum?:number };
type BuildState = { class_key:string; spec_key:string; equipment:EquipmentState[]; consumable_ids:number[]; objectives:Objective[]; constraints:Record<string,unknown> };
type Session = { session_id:string; state:BuildState; source_loadout_id?:number|null };
type Calculation = {
  ratings:Stats; percentages:Stats;
  equipment_totals:{ primary_stat:string; primary_stat_value:number; stamina:number; armor:number; armor_complete:boolean };
  supplements:{ name_zh_cn:string; category:string; included_in_secondary_stats:boolean }[];
};
type Solution = { equipment:Item[]; ratings:Stats; percentages:Stats; consumable_ids:number[]; crafted_item_count:number; tier_count:number; late_raid_special_effect_count:number };
type Loadout = { id:number; name:string; creator_name:string; class_key:string; spec_key:string; is_favorite:boolean; updated_at:string };
type ConversationSummary = { id:number; title:string; class_key:string; spec_key:string; message_count:number; has_compressed_context:boolean; created_at:string; updated_at:string };
type ConversationMessage = { id:number; role:"user"|"assistant"; content:string; proposal?:{solutions?:Solution[]}|null; created_at:string };
type Conversation = ConversationSummary & { session_id:string; state:BuildState; source_loadout_id?:number|null; messages:ConversationMessage[] };

const API = "/api/v1";
const statNames:Record<StatKey,string> = { critical_strike:"暴击", haste:"急速", mastery:"精通", versatility:"全能" };
const statColors:Record<StatKey,string> = { critical_strike:"purple", haste:"cyan", mastery:"green", versatility:"amber" };
const slotNames:Record<string,string> = { head:"头部",neck:"项链",shoulders:"肩部",back:"披风",chest:"胸部",wrist:"护腕",gloves:"手部",waist:"腰带",legs:"腿部",feet:"鞋子",finger:"戒指",trinket:"饰品",weapon:"主手",off_hand:"副手" };
const leftSlots = ["head","neck","shoulders","back","chest","wrist","gloves","waist"];
const rightSlots = ["legs","feet","finger","finger","trinket","trinket","weapon","off_hand"];

async function json<T>(url:string, init?:RequestInit):Promise<T> {
  const response = await fetch(url, { ...init, headers:{ "Content-Type":"application/json", ...(init?.headers || {}) } });
  if (!response.ok) throw new Error((await response.text()) || `HTTP ${response.status}`);
  return response.json();
}

function refreshWowhead() {
  window.setTimeout(() => (window as unknown as {$WowheadPower?:{refreshLinks:()=>void}}).$WowheadPower?.refreshLinks(), 0);
}

function itemSlot(item:Item) { return item.display_slot_key || item.slot_key; }
function placeWeapons(values:Item[]) { let main=0;return values.map(item=>itemSlot(item)==="weapon"?{...item,display_slot_key:main++?"off_hand":"weapon"}:item); }
function itemStats(item:Item) {
  return (Object.entries(item.stats) as [StatKey,number][]).filter(([,value])=>value).map(([key,value])=>`${statNames[key]} ${value}`).join(" · ") || "特效装备";
}
function withCraftedStats(item:Item, selected:Partial<Stats>={}) {
  return {...item,stats:(Object.keys(statNames) as StatKey[]).reduce((values,key)=>({...values,[key]:(item.stats[key]||0)+(selected[key]||0)}),{} as Stats)};
}
function ratios(ratings:Stats) {
  const values = Object.values(ratings).filter(value=>value>0);
  const base = values.length ? Math.min(...values) : 1;
  return (Object.keys(statNames) as StatKey[]).map(key=>(ratings[key]/base).toFixed(1));
}

function useSpecs() {
  const [specs,setSpecs] = useState<Spec[]>([]);
  useEffect(()=>{ json<Spec[]>(`${API}/catalog/specs`).then(setSpecs).catch(()=>setSpecs([])); },[]);
  return specs;
}

const specIconIds:Record<string,number> = {
  "mage.arcane":135932,"mage.fire":135810,"mage.frost":135846,
  "paladin.holy":135920,"paladin.protection":236264,"paladin.retribution":135873,
  "warrior.arms":132355,"warrior.fury":132347,"warrior.protection":132341,
  "druid.balance":136096,"druid.feral":132115,"druid.guardian":132276,"druid.restoration":136041,
  "death_knight.blood":135770,"death_knight.frost":135773,"death_knight.unholy":135775,
  "hunter.beast_mastery":461112,"hunter.marksmanship":236179,"hunter.survival":461113,
  "priest.discipline":135940,"priest.holy":237542,"priest.shadow":136207,
  "rogue.assassination":236270,"rogue.outlaw":236286,"rogue.subtlety":132320,
  "shaman.elemental":136048,"shaman.enhancement":237581,"shaman.restoration":136052,
  "warlock.affliction":136145,"warlock.demonology":136172,"warlock.destruction":136186,
  "monk.brewmaster":608951,"monk.windwalker":608953,"monk.mistweaver":608952,
  "demon_hunter.havoc":1247264,"demon_hunter.vengeance":1247265,"demon_hunter.devourer":7455385,
  "evoker.devastation":4511811,"evoker.preservation":4511812,"evoker.augmentation":5198700,
};
function specIcon(specKey:string) { return `https://render.worldofwarcraft.com/us/icons/56/${specIconIds[specKey]||135932}.jpg`; }

function SpecPicker({specs,value,onChange}:{specs:Spec[];value:string;onChange:(value:string)=>void|Promise<void>}) {
  const current=specs.find(item=>item.key===value);
  return <details className="spec-picker">
    <summary><img src={specIcon(value)} alt=""/><span>{current?`${current.class_name_zh_cn} · ${current.spec_name_zh_cn}`:"选择职业专精"}</span><i>⌄</i></summary>
    <div className="spec-menu">{specs.map(item=><button key={item.key} className={item.key===value?"active":""} onClick={event=>{event.currentTarget.closest("details")?.removeAttribute("open");onChange(item.key)}}><img src={specIcon(item.key)} alt=""/><span><b>{item.class_name_zh_cn}</b><small>{item.spec_name_zh_cn}</small></span></button>)}</div>
  </details>;
}

function DungeonRoutes({items}:{items:Item[]}) {
  const sourceLabel=(type:string)=>type==="raid"?"团本":type==="world_boss"?"世界首领":"大秘境";
  const routes=useMemo(()=>{const groups=new Map<string,{name:string;type:string;items:Item[];score:number}>();items.forEach(item=>{const source=item.sources?.find(value=>value.instance_name_zh_cn);if(!source?.instance_name_zh_cn)return;const group=groups.get(source.instance_name_zh_cn)||{name:source.instance_name_zh_cn,type:source.source_type,items:[],score:0};group.items.push(item);group.score+=1+(item.has_special_effect?2:0);groups.set(group.name,group)});return [...groups.values()].sort((a,b)=>b.score-a.score)},[items]);
  return <section className="build-routes"><header><div><h2>刷本提升路线</h2><span>根据当前目标配装统计装备来源</span></div><b>{routes.length} 个来源</b></header>{!routes.length?<div className="route-empty">应用配装方案后，这里会自动汇总优先获取路线</div>:<div className="build-route-grid">{routes.map((route,index)=><article key={route.name}><header><div><em>优先级 #{index+1}</em><h3>{route.name}</h3></div><span>{sourceLabel(route.type)} · {route.items.length} 件</span></header>{route.items.map(item=><div key={`${item.item_id}-${itemSlot(item)}`}><img src={item.icon_url||""} alt=""/><span><strong>{item.name_zh_cn}</strong><small>{slotNames[itemSlot(item)]} · {item.sources.find(value=>value.instance_name_zh_cn===route.name)?.encounter_name_zh_cn||itemStats(item)}</small></span>{item.has_special_effect&&<em>特效</em>}</div>)}</article>)}</div>}</section>;
}

function GearEntry({slot,item,side,equipment,gems,onReplace,onRemove}:{slot:string;item?:Item;side:"left"|"right";equipment?:EquipmentState;gems:Map<number,Gem>;onReplace:()=>void;onRemove:()=>void}) {
  if (!item) return <div className={`gear-entry empty ${side}`}>
    <span className="gear-slot">{slotNames[slot]}</span><span className="empty-icon">＋</span>
    <span className="empty-text">尚未选择装备</span><button className="replace-button" onClick={onReplace}>选择</button>
  </div>;
  const source=item.sources?.[0];
  const inserted=equipment?.gems||[];
  const sockets=Math.max(item.current_sockets||0,inserted.length);
  return <div className={`gear-entry ${side}`}>
    <span className="gear-slot">{slotNames[slot]}</span>
    <a className="gear-icon" href={item.wowhead_url} data-wowhead={item.wowhead_data} target="_blank" rel="noreferrer"><img src={item.icon_url||""} alt=""/></a>
    <div className="gear-main"><div><a className="epic" href={item.wowhead_url} data-wowhead={item.wowhead_data} target="_blank" rel="noreferrer">{item.name_zh_cn}</a><b>{item.item_level}</b></div>{sockets>0&&<div className="socket-row">{Array.from({length:sockets},(_,index)=>{const gem=gems.get(inserted[index]);return gem?<img key={index} src={`https://wow.zamimg.com/images/wow/icons/small/${gem.icon}.jpg`} title={gem.name_zh_cn} alt={gem.name_zh_cn}/>:<i key={index} title="空宝石插槽">◇</i>})}</div>}<div className="gear-stats">{(Object.entries(item.stats) as [StatKey,number][]).filter(([,value])=>value).map(([key,value],index)=><span className={statColors[key]} key={key}>{index>0&&<i>/</i>}{statNames[key]} {value}</span>)}</div><small>{source?.instance_name_zh_cn||"制造"}{source?.encounter_name_zh_cn?` · ${source.encounter_name_zh_cn}`:""}</small></div>
    <div className="gear-tags">{item.has_special_effect&&<em>特效</em>}{item.is_crafted&&<em className="craft">制造</em>}{item.catalyst_eligible&&<em className="tier">可转化</em>}</div>
    <button className="replace-button" onClick={onReplace}>更换</button>
    <button className="remove-button" onClick={onRemove} aria-label={`移除${item.name_zh_cn}`}>×</button>
  </div>;
}

function StatSummary({calculation,state}:{calculation:Calculation|null;state:BuildState|null}) {
  const primaryNames:Record<string,string>={intellect:"智力",strength:"力量",agility:"敏捷"};
  const target=state?.objectives.find(value=>value.rule==="rating_ratio")?.weights;
  const currentRatio=calculation?ratios(calculation.ratings):[];
  const maxRating=calculation?Math.max(...Object.values(calculation.ratings),1):1;
  return <section className="stat-summary">
    <header><div><h2>属性合计</h2><span>静态属性实时计算</span></div><small>合剂计入 · 宝石暂不计</small></header>
    {!calculation?<div className="summary-empty">完成整套配装后显示精确属性与面板百分比</div>:<>
      <div className="primary-cards"><div><span>{primaryNames[calculation.equipment_totals.primary_stat]||"主属性"}</span><b>{calculation.equipment_totals.primary_stat_value.toLocaleString()}</b></div><div><span>耐力</span><b>{calculation.equipment_totals.stamina.toLocaleString()}</b></div><div><span>护甲</span><b>{calculation.equipment_totals.armor_complete?calculation.equipment_totals.armor.toLocaleString():"待补数据"}</b></div></div>
      <div className="stat-detail"><div className="stat-bars">{(Object.keys(statNames) as StatKey[]).map((key,index)=><div className={`stat-line ${statColors[key]}`} key={key}><span>{statNames[key]}</span><i><u style={{width:`${calculation.ratings[key]/maxRating*100}%`}}/></i><b>{calculation.ratings[key].toLocaleString()}</b><em>{calculation.percentages[key].toFixed(1)}%</em><small>{currentRatio[index]}</small></div>)}</div><div className="ratio-card"><span>实际比例</span><b>{currentRatio.join(" : ")}</b><span>目标比例</span><b>{target?(Object.keys(statNames) as StatKey[]).map(key=>target[key]||0).join(" : "):"未设置"}</b></div></div>
      <div className="supplements">{calculation.supplements.filter(value=>value.included_in_secondary_stats).map(value=><span key={value.name_zh_cn}>✓ 已计入 {value.name_zh_cn}</span>)}</div>
    </>}
  </section>;
}

function ProposalCard({solution,index,onApply,onApplyItem}:{solution:Solution;index:number;onApply:()=>void;onApplyItem:(item:Item)=>void}) {
  const max=Math.max(...Object.values(solution.percentages),1);
  return <article className={`proposal-card ${index===0?"recommended":""}`}><header><div><b>方案 {String.fromCharCode(65+index)}</b><span>{index===0?"推荐方案":"备选方案"}</span></div><em>{solution.late_raid_special_effect_count} 件尾王特效</em></header><div className="proposal-bars">{(Object.keys(statNames) as StatKey[]).map(key=><div className={statColors[key]} key={key}><span>{statNames[key]}</span><i><u style={{width:`${solution.percentages[key]/max*100}%`}}/></i><b>{solution.percentages[key].toFixed(1)}%</b></div>)}</div><div className="proposal-meta"><span>实际比例 <b>{ratios(solution.ratings).join(" : ")}</b></span><span>{solution.tier_count} 套装 · {solution.crafted_item_count} 制造</span></div><details className="proposal-items"><summary>查看并选择单件装备</summary>{placeWeapons(solution.equipment).map(item=><button key={`${itemSlot(item)}-${item.item_id}`} onClick={()=>onApplyItem(item)}><span>{slotNames[itemSlot(item)]}</span><b>{item.name_zh_cn}</b><em>选用</em></button>)}</details><button onClick={onApply}>应用整套方案</button></article>;
}

function BuilderPage({specs}:{specs:Spec[]}) {
  const [spec,setSpec] = useState(localStorage.getItem("wow-spec")||"mage.arcane");
  const [session,setSession] = useState<Session|null>(null);
  const [items,setItems] = useState<Item[]>([]);
  const [calculation,setCalculation] = useState<Calculation|null>(null);
  const [messages,setMessages] = useState<{role:"user"|"assistant";text:string}[]>([{role:"assistant",text:"告诉我你的属性比例或面板百分比目标，我会调用装备搜索和确定性计算工具生成方案。"}]);
  const [conversations,setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId,setConversationId] = useState<number|null>(null);
  const [input,setInput] = useState("");
  const [busy,setBusy] = useState(false);
  const [solutions,setSolutions] = useState<Solution[]>([]);
  const [loadouts,setLoadouts] = useState<Loadout[]>([]);
  const [showSaves,setShowSaves] = useState(false);
  const [saveDraft,setSaveDraft] = useState<{mode:"overwrite"|"copy";name:string;creator_name:string}|null>(null);
  const [saveError,setSaveError] = useState("");
  const [saving,setSaving] = useState(false);
  const [notice,setNotice] = useState("");
  const [picker,setPicker] = useState<{slot:string;current?:Item}|null>(null);
  const [candidates,setCandidates] = useState<Item[]>([]);
  const [pickerBusy,setPickerBusy] = useState(false);
  const [crafting,setCrafting] = useState<{item:Item;selected:StatKey[]}|null>(null);
  const [gems,setGems] = useState<Gem[]>([]);

  useEffect(()=>{json<Gem[]>(`${API}/catalog/gems`).then(setGems).catch(()=>setGems([]))},[]);

  async function fetchItems(state:BuildState) {
    if (!state.equipment.length) return [];
    const levels=[...new Set(state.equipment.map(value=>value.item_level))];
    const found=(await Promise.all(levels.map(level=>{const query=new URLSearchParams({item_level:String(level),class_key:state.class_key,spec_key:state.spec_key,limit:"100"});state.equipment.filter(value=>value.item_level===level).forEach(value=>query.append("item_ids",String(value.item_id)));return json<{items:Item[]}>(`${API}/loot/items?${query}`)}))).flatMap(value=>value.items);
    return placeWeapons(state.equipment.map(selected=>{const item=found.find(value=>value.item_id===selected.item_id&&value.item_level===selected.item_level);const displayed=item?withCraftedStats(item,selected.crafted_secondary_stats):item;return displayed&&selected.equipped_slot?{...displayed,display_slot_key:selected.equipped_slot}:displayed}).filter(Boolean) as Item[]);
  }
  async function fetchStats(id:string) {
    const result=await json<{success:boolean;calculation?:Calculation}>(`${API}/builder/sessions/${id}/stats`);
    setCalculation(result.success?result.calculation!:null);
  }
  async function hydrate(current:Session) {
    setSession(current);setSpec(`${current.state.class_key}.${current.state.spec_key}`);
    const resolved=await fetchItems(current.state);setItems(resolved);refreshWowhead();
    await fetchStats(current.session_id);
    return current;
  }
  async function refreshConversations() {
    const values=await json<ConversationSummary[]>(`${API}/conversations`);setConversations(values);return values;
  }
  async function openConversation(id:number) {
    const detail=await json<Conversation>(`${API}/conversations/${id}`);
    sessionStorage.setItem("wow-conversation",String(id));localStorage.setItem("wow-spec",`${detail.class_key}.${detail.spec_key}`);
    setConversationId(id);setMessages(detail.messages.length?detail.messages.map(value=>({role:value.role,text:value.content})):[{role:"assistant",text:"告诉我你的属性比例或面板百分比目标，我会调用装备搜索和确定性计算工具生成方案。"}]);
    setSolutions([]);
    return hydrate({session_id:detail.session_id,state:detail.state,source_loadout_id:detail.source_loadout_id||null});
  }
  async function createConversation(chosen=spec,loadoutId?:number,title?:string) {
    const detail=await json<Conversation>(`${API}/conversations`,{method:"POST",body:JSON.stringify(loadoutId?{loadout_id:loadoutId,title}:{spec:chosen,title})});
    await refreshConversations();await openConversation(detail.id);return {session_id:detail.session_id,state:detail.state,source_loadout_id:loadoutId||null} as Session;
  }
  async function patchEquipment(current:Session,equipment:EquipmentState[],displayItems?:Item[]) {
    const next=await json<Session>(`${API}/builder/sessions/${current.session_id}`,{method:"PATCH",body:JSON.stringify({equipment})});
    setSession(next);setItems(displayItems||await fetchItems(next.state));refreshWowhead();await fetchStats(next.session_id);return next;
  }
  useEffect(()=>{(async()=>{let current:Session;const values=await refreshConversations();const saved=Number(sessionStorage.getItem("wow-conversation"));const target=values.find(value=>value.id===saved);current=target?await openConversation(target.id):await createConversation();const raw=localStorage.getItem("wow-pending-item");if(raw){localStorage.removeItem("wow-pending-item");const pending=JSON.parse(raw) as Item;const currentItems=await fetchItems(current.state);const existing=currentItems.find(value=>itemSlot(value)===itemSlot(pending));if(pending.customizable_secondaries){setPicker({slot:itemSlot(pending),current:existing});setCrafting({item:pending,selected:[]})}else{const equipment=current.state.equipment.filter(value=>value.item_id!==existing?.item_id);equipment.push({item_id:pending.item_id,item_level:pending.item_level,gems:[],crafted_secondary_stats:{}});await patchEquipment(current,equipment,[...currentItems.filter(value=>value.item_id!==existing?.item_id),pending])}}})().catch(()=>{})},[]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(()=>{const timer=window.setInterval(()=>refreshConversations().catch(()=>{}),5000);return()=>window.clearInterval(timer)},[]); // eslint-disable-line react-hooks/exhaustive-deps

  const grouped=useMemo(()=>{const map:Record<string,Item[]>={};items.forEach(item=>(map[itemSlot(item)]??=[]).push(item));return map},[items]);
  const occurrence=(slots:string[],index:number)=>slots.slice(0,index).filter(value=>value===slots[index]).length;
  const take=(slot:string,index=0)=>grouped[slot]?.[index];
  const selected=(item?:Item)=>item?session?.state.equipment.find(value=>value.item_id===item.item_id&&value.item_level===item.item_level):undefined;
  const gemMap=useMemo(()=>new Map(gems.map(gem=>[gem.id,gem])),[gems]);
  async function removeItem(item?:Item){if(!item||!session)return;await patchEquipment(session,session.state.equipment.filter(value=>value.item_id!==item.item_id),items.filter(value=>value.item_id!==item.item_id))}
  async function openPicker(slot:string,current?:Item){setPicker({slot,current});setCrafting(null);setPickerBusy(true);setCandidates([]);const [class_key,spec_key]=spec.split(".");const load=(item_level:number)=>json<{items:Item[]}>(`${API}/loot/items?${new URLSearchParams({item_level:String(item_level),class_key,spec_key,slot_key:slot,limit:"200"})}`);const [drops,crafted]=await Promise.all([load(334),load(331)]);setCandidates([...drops.items,...crafted.items.filter(value=>value.is_crafted)]);setPickerBusy(false);refreshWowhead()}
  async function chooseItem(item:Item,craftedStats:Partial<Stats>={},targetSlot=picker?.slot){if(!session||!targetSlot)return;if(item.customizable_secondaries&&!Object.keys(craftedStats).length){setPicker({slot:targetSlot,current:items.find(value=>itemSlot(value)===targetSlot)});setCrafting({item,selected:[]});return}const current=picker?.slot===targetSlot?picker.current:items.find(value=>itemSlot(value)===targetSlot);const replacingWeapon=targetSlot==="weapon"&&Boolean(item.weapon_type?.startsWith("2h_")||item.weapon_type?.startsWith("ranged_"));const replacingOffhand=targetSlot==="off_hand";const removed=items.filter(value=>value.item_id===current?.item_id||(replacingWeapon&&["weapon","off_hand"].includes(itemSlot(value)))||(replacingOffhand&&itemSlot(value)==="weapon"&&Boolean(value.weapon_type?.startsWith("2h_")||value.weapon_type?.startsWith("ranged_"))));const removedIds=new Set(removed.map(value=>value.item_id));const equipment=session.state.equipment.filter(value=>!removedIds.has(value.item_id));equipment.push({item_id:item.item_id,item_level:item.item_level,gems:[],crafted_secondary_stats:craftedStats,catalyst_tier_item_id:item.catalyst_tier_item_id||null,equipped_slot:targetSlot==="off_hand"?"off_hand":targetSlot==="weapon"?"weapon":null});const displayed=withCraftedStats({...item,display_slot_key:targetSlot},craftedStats);await patchEquipment(session,equipment,[...items.filter(value=>!removedIds.has(value.item_id)),displayed]);setCrafting(null);setPicker(null)}
  async function applySolution(solution:Solution){if(!session)return;const equipment=solution.equipment.map(item=>({item_id:item.item_id,item_level:item.item_level,crafted_secondary_stats:(item as unknown as {selected_crafted_secondary_stats?:Partial<Stats>}).selected_crafted_secondary_stats||{},catalyst_tier_item_id:item.catalyst_tier_item_id||null}));const next=await json<Session>(`${API}/builder/sessions/${session.session_id}`,{method:"PATCH",body:JSON.stringify({equipment,consumable_ids:solution.consumable_ids})});setSession(next);setItems(placeWeapons(solution.equipment));setSolutions([]);refreshWowhead();await fetchStats(next.session_id)}
  async function send(event:FormEvent){event.preventDefault();if(!input.trim()||!session||busy)return;const text=input.trim();setInput("");setBusy(true);setSolutions([]);setMessages(value=>[...value,{role:"user",text},{role:"assistant",text:""}]);try{const response=await fetch(`${API}/builder/sessions/${session.session_id}/messages/stream`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({message:text})});if(!response.ok||!response.body)throw new Error("对话请求失败");const reader=response.body.getReader();const decoder=new TextDecoder();let buffer="";while(true){const {done,value}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});const blocks=buffer.split("\n\n");buffer=blocks.pop()||"";for(const block of blocks){const eventName=block.match(/^event: (.+)$/m)?.[1];const line=block.match(/^data: (.+)$/m)?.[1];if(!line)continue;const data=JSON.parse(line);if(eventName==="text_delta")setMessages(list=>list.map((message,index)=>index===list.length-1?{...message,text:message.text+data.text}:message));if(eventName==="proposal"&&data?.solutions)setSolutions(data.solutions);if(eventName==="state")setSession(current=>current?{...current,state:data}:current);if(eventName==="error")throw new Error("Agent 暂时不可用")}if(done)break}}catch(error){setMessages(list=>list.map((message,index)=>index===list.length-1?{...message,text:error instanceof Error?error.message:"请求失败"}:message))}finally{setBusy(false);refreshConversations().catch(()=>{})}}
  async function openSaves(){setShowSaves(true);setLoadouts(await json<Loadout[]>(`${API}/loadouts`))}
  async function openLoadout(id:number){const saved=loadouts.find(value=>value.id===id);await createConversation(`${saved?.class_key}.${saved?.spec_key}`,id,saved?.name);setShowSaves(false)}
  async function clearChat(){if(!conversationId||!confirm("清空这个对话的消息和上下文？当前装备会保留。"))return;const detail=await json<Conversation>(`${API}/conversations/${conversationId}/clear`,{method:"POST"});setMessages([{role:"assistant",text:"对话上下文已清空，当前装备仍然保留。"}]);setSolutions([]);setSession({session_id:detail.session_id,state:detail.state,source_loadout_id:detail.source_loadout_id||null});await refreshConversations()}
  async function renameConversation(id:number,current:string){const title=prompt("对话名称",current)?.trim();if(!title)return;await json(`${API}/conversations/${id}`,{method:"PATCH",body:JSON.stringify({title})});await refreshConversations()}
  async function removeConversation(id:number){if(!confirm("删除这个对话及其消息历史？已保存的配装方案不会删除。"))return;await json(`${API}/conversations/${id}`,{method:"DELETE"});const values=await refreshConversations();if(id===conversationId){if(values[0])await openConversation(values[0].id);else await createConversation(spec)}}
  async function openSave(mode:"overwrite"|"copy"=session?.source_loadout_id?"overwrite":"copy") {if(!session)return;const values=await json<Loadout[]>(`${API}/loadouts`);setLoadouts(values);const source=values.find(value=>value.id===session.source_loadout_id);setSaveError("");setSaveDraft({mode,name:mode==="overwrite"&&source?source.name:(conversations.find(value=>value.id===conversationId)?.title||"新配装方案"),creator_name:source?.creator_name||localStorage.getItem("wow-creator")||"Broo"})}
  async function submitSave(event:FormEvent){event.preventDefault();if(!session||!saveDraft||saving)return;setSaving(true);setSaveError("");try{const overwrite=saveDraft.mode==="overwrite"&&session.source_loadout_id;const saved=await json<Loadout>(overwrite?`${API}/loadouts/${session.source_loadout_id}`:`${API}/loadouts`,{method:overwrite?"PATCH":"POST",body:JSON.stringify({name:saveDraft.name.trim(),creator_name:saveDraft.creator_name.trim(),builder_session_id:session.session_id})});localStorage.setItem("wow-creator",saved.creator_name);setSession(current=>current?{...current,source_loadout_id:saved.id}:current);setSaveDraft(null);setNotice(overwrite?"方案修改已保存":"已另存为新方案");setTimeout(()=>setNotice(""),2200)}catch(error){setSaveError(error instanceof Error?error.message:"保存失败")}finally{setSaving(false)}}
  async function renameLoadout(value:Loadout){const name=prompt("方案名称",value.name)?.trim();if(!name)return;await json(`${API}/loadouts/${value.id}`,{method:"PATCH",body:JSON.stringify({name})});setLoadouts(await json<Loadout[]>(`${API}/loadouts`))}
  async function removeLoadout(value:Loadout){if(!confirm(`删除方案“${value.name}”？`))return;await json(`${API}/loadouts/${value.id}`,{method:"DELETE"});setLoadouts(await json<Loadout[]>(`${API}/loadouts`));if(session?.source_loadout_id===value.id)setSession(current=>current?{...current,source_loadout_id:null}:current)}

  return <main className="workspace builder-page">
    <section className="page-toolbar"><div><span className="toolbar-icon">◆</span><h1>AI智能配装助手</h1></div><SpecPicker specs={specs} value={spec} onChange={async value=>{setSpec(value);await createConversation(value)}}/><div className="toolbar-actions"><button disabled title="下一阶段接入">☁ 导入 SimC</button><button onClick={openSaves}>◷ 历史方案</button><button>▥ 对比方案</button><button className="primary" onClick={()=>openSave()} disabled={!session}>▣ {session?.source_loadout_id?"保存修改":"保存方案"}</button></div></section>
    <div className="conversation-workspace">
      <aside className="conversation-sidebar app-panel"><header><div><h2>配装对话</h2><span>独立上下文</span></div><button onClick={()=>createConversation(spec)} aria-label="新建对话">＋ 新对话</button></header><div className="conversation-list">{conversations.map(value=><article className={value.id===conversationId?"active":""} key={value.id}><button className="conversation-open" onClick={()=>openConversation(value.id)}><span>{value.title}</span><small>{specs.find(item=>item.key===`${value.class_key}.${value.spec_key}`)?.spec_name_zh_cn||value.spec_key} · {value.message_count} 条消息</small>{value.has_compressed_context&&<em>已压缩上下文</em>}</button><div><button onClick={()=>renameConversation(value.id,value.title)} aria-label={`重命名${value.title}`}>改</button><button className="danger" onClick={()=>removeConversation(value.id)} aria-label={`删除${value.title}`}>删</button></div></article>)}</div></aside>
      <div className="conversation-main">
      <section className="scheme-bar"><span>方案名称</span><b>{conversations.find(value=>value.id===conversationId)?.title||`${specs.find(value=>value.key===spec)?.spec_name_zh_cn||"当前"}配装`}</b><span>神话 6/6 · 334</span>{session?.source_loadout_id&&<span>已关联保存方案 #{session.source_loadout_id}</span>}<em>{items.length}/16 已选择</em></section>
      <div className="builder-layout">
      <section className="equipment-panel app-panel"><header><div><h2>当前装备</h2><span>装备名称可查看中文 Wowhead 详情</span></div><em className={items.length===16?"complete":""}>{items.length}/16 {items.length===16?"完整":"配装中"}</em></header><div className="gear-columns"><div>{leftSlots.map((slot,index)=>{const item=take(slot,occurrence(leftSlots,index));return <GearEntry key={`${slot}-${index}`} slot={slot} side="left" item={item} equipment={selected(item)} gems={gemMap} onReplace={()=>openPicker(slot,item)} onRemove={()=>removeItem(item)}/>})}</div><div>{rightSlots.map((slot,index)=>{const item=take(slot,occurrence(rightSlots,index));return <GearEntry key={`${slot}-${index}`} slot={slot} side="right" item={item} equipment={selected(item)} gems={gemMap} onReplace={()=>openPicker(slot,item)} onRemove={()=>removeItem(item)}/>})}</div></div><StatSummary calculation={calculation} state={session?.state||null}/><DungeonRoutes items={items}/></section>
      <section className="chat-panel app-panel"><header><div><h2>AI 配装对话</h2><span>✓ 独立上下文 · 自动压缩</span></div><button onClick={clearChat}>清空对话</button></header><div className="messages">{messages.map((message,index)=><div className={`message ${message.role}`} key={index}>{message.text?(message.role==="assistant"?<ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>:message.text):<span className="typing">•••</span>}</div>)}{solutions.length>0&&<div className="proposal-grid">{solutions.map((solution,index)=><ProposalCard key={index} solution={solution} index={index} onApply={()=>applySolution(solution)} onApplyItem={item=>chooseItem(item,item.selected_crafted_secondary_stats||{},itemSlot(item))}/>)}</div>}</div><div className="quick-prompts"><button onClick={()=>setInput("把急速提高到20%左右")}>急速提高到20%</button><button onClick={()=>setInput("少用一件制造装备")}>少用一件制造装</button><button onClick={()=>setInput("保留当前两个饰品")}>保留两个饰品</button><button onClick={()=>setInput("优先选择尾王特效装备")}>优先尾王特效</button></div><form onSubmit={send}><textarea rows={3} value={input} onChange={event=>setInput(event.target.value)} placeholder="描述你的属性目标或想保留的装备…"/><button className="send-button" disabled={busy||!input.trim()}>{busy?"计算中":"发送"}</button></form></section>
      </div>
      </div>
    </div>
    {notice&&<div className="toast" role="status" aria-live="polite">✓ {notice}</div>}
    {saveDraft&&<Modal onClose={()=>!saving&&setSaveDraft(null)} title={saveDraft.mode==="overwrite"?"保存方案修改":"另存为新方案"}><form className="save-form" onSubmit={submitSave}><label>方案名称<input autoFocus required maxLength={120} value={saveDraft.name} onChange={event=>setSaveDraft({...saveDraft,name:event.target.value})}/></label><label>创建人<input required maxLength={64} value={saveDraft.creator_name} onChange={event=>setSaveDraft({...saveDraft,creator_name:event.target.value})}/></label>{saveError&&<p role="alert">{saveError}</p>}<footer>{session?.source_loadout_id&&<button type="button" onClick={()=>setSaveDraft({...saveDraft,mode:saveDraft.mode==="overwrite"?"copy":"overwrite"})}>{saveDraft.mode==="overwrite"?"改为另存为":"改为覆盖原方案"}</button>}<button className="primary" disabled={saving||!saveDraft.name.trim()||!saveDraft.creator_name.trim()}>{saving?"保存中…":saveDraft.mode==="overwrite"?"保存修改":"另存为"}</button></footer></form></Modal>}
    {showSaves&&<Modal onClose={()=>setShowSaves(false)} title="历史方案"><div className="saved-list">{loadouts.map(value=><article key={value.id}><div><strong>{value.name}</strong><span>{value.creator_name} · {value.class_key}.{value.spec_key}</span><small>{new Date(value.updated_at).toLocaleString()}</small></div><footer><button className="primary" onClick={()=>openLoadout(value.id)}>导入新对话</button><button onClick={()=>renameLoadout(value)}>重命名</button><button className="danger" onClick={()=>removeLoadout(value)}>删除</button></footer></article>)}{!loadouts.length&&<p>还没有保存方案</p>}</div></Modal>}
    {picker&&<Modal onClose={()=>{setCrafting(null);setPicker(null)}} title={crafting?`选择「${crafting.item.name_zh_cn}」绿字`:`更换${slotNames[picker.slot]}`} wide>{crafting?<div className="craft-picker"><p>选择 {crafting.item.customizable_secondary_amounts?.length||0} 项制造属性</p><div>{(crafting.item.secondary_stat_choices||[]).map(key=>{const active=crafting.selected.includes(key);const count=crafting.item.customizable_secondary_amounts?.length||0;return <button className={active?"active":""} key={key} onClick={()=>setCrafting({...crafting,selected:active?crafting.selected.filter(value=>value!==key):crafting.selected.length<count?[...crafting.selected,key]:crafting.selected})}>{statNames[key]}</button>})}</div><footer><button onClick={()=>setCrafting(null)}>返回</button><button className="primary" disabled={crafting.selected.length!==(crafting.item.customizable_secondary_amounts?.length||0)} onClick={()=>chooseItem(crafting.item,Object.fromEntries(crafting.selected.map((key,index)=>[key,crafting.item.customizable_secondary_amounts?.[index]||0])) as Partial<Stats>)}>确认属性</button></footer></div>:<div className="picker-list">{pickerBusy?<p>正在读取当前专精可用装备…</p>:candidates.map(item=><button className="picker-item" key={`${item.item_id}-${item.item_level}`} onClick={()=>chooseItem(item)}><img src={item.icon_url||""} alt=""/><span><strong>{item.name_zh_cn}</strong><small>{item.item_level} · {item.customizable_secondaries?`可自选 ${item.customizable_secondary_amounts?.length||0} 项绿字`:itemStats(item)}</small><small>{item.sources[0]?.instance_name_zh_cn||"制造"}</small></span>{item.is_crafted?<em>制造</em>:item.has_special_effect&&<em>特效</em>}</button>)}</div>}</Modal>}
  </main>;
}

function Modal({title,onClose,children,wide=false}:{title:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}) {
  return <div className="modal-backdrop" onClick={onClose}><section className={`modal ${wide?"wide":""}`} onClick={event=>event.stopPropagation()}><header><h2>{title}</h2><button onClick={onClose}>×</button></header>{children}</section></div>;
}

function LootPage({specs}:{specs:Spec[]}) {
  const [spec,setSpec]=useState(localStorage.getItem("wow-spec")||"mage.arcane");
  const [itemLevel,setItemLevel]=useState(334);
  const [instances,setInstances]=useState<{source_type:string;name_zh_cn:string}[]>([]);
  const [items,setItems]=useState<Item[]>([]);
  const [instance,setInstance]=useState("");const [slot,setSlot]=useState("");const [query,setQuery]=useState("");const [sourceType,setSourceType]=useState("");const [special,setSpecial]=useState(false);const [selectedStats,setSelectedStats]=useState<string[]>([]);const [loading,setLoading]=useState(false);
  useEffect(()=>{json<{source_type:string;name_zh_cn:string}[]>(`${API}/loot/instances`).then(setInstances)},[]);
  async function search(){setLoading(true);const [class_key,spec_key]=spec.split(".");const params=new URLSearchParams({item_level:String(itemLevel),class_key,spec_key,limit:"300"});if(instance)params.set("instance_name",instance);if(slot)params.set("slot_key",slot==="off_hand"?"weapon":slot);if(query)params.set("q",query);if(sourceType)params.set("source_type",sourceType);if(special)params.set("has_special_effect","true");selectedStats.forEach(value=>params.append("secondary_stats",value));const result=await json<{items:Item[]}>(`${API}/loot/items?${params}`);setItems(result.items.filter(value=>slot!=="off_hand"||itemSlot(value)==="off_hand"));setLoading(false);refreshWowhead()}
  useEffect(()=>{search().catch(()=>setLoading(false))},[spec,itemLevel,instance,slot,special,sourceType,selectedStats.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  const toggleStat=(value:string)=>setSelectedStats(current=>current.includes(value)?current.filter(item=>item!==value):[...current,value]);
  const addToBuilder=(item:Item)=>{localStorage.setItem("wow-pending-item",JSON.stringify(item));location.href="/builder"};
  const reset=()=>{setItemLevel(334);setInstance("");setSlot("");setSourceType("");setSpecial(false);setSelectedStats([])};
  return <main className="workspace loot-page"><section className="database-toolbar"><div><h1>副本掉落与装备数据库</h1><span>当前赛季 · {items.length} 件符合条件装备</span></div><form onSubmit={event=>{event.preventDefault();search()}}><input value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索中文或英文装备名称"/><button>搜索</button></form><select value={spec} onChange={event=>{setSpec(event.target.value);localStorage.setItem("wow-spec",event.target.value)}}>{specs.map(value=><option value={value.key} key={value.key}>{value.class_name_zh_cn} · {value.spec_name_zh_cn}</option>)}</select><select value={itemLevel} onChange={event=>setItemLevel(Number(event.target.value))}><option value={334}>神话 6/6 · 334</option><option value={321}>英雄 6/6 · 321</option><option value={318}>英雄 5/6 · 318</option><option value={315}>英雄 4/6 · 315</option><option value={311}>英雄 3/6 · 311</option><option value={308}>英雄 2/6 · 308</option><option value={305}>英雄 1/6 · 305</option></select></section><div className="loot-layout">
    <aside className="filter-panel app-panel"><header><h2>筛选条件</h2><button onClick={reset}>清空重置</button></header><label>来源类型</label><div className="source-tabs"><button className={!sourceType?"active":""} onClick={()=>setSourceType("")}>全部</button><button className={sourceType==="dungeon"?"active":""} onClick={()=>setSourceType("dungeon")}>大秘境</button><button className={sourceType==="raid"?"active":""} onClick={()=>setSourceType("raid")}>团本</button><button className={sourceType==="world_boss"?"active":""} onClick={()=>setSourceType("world_boss")}>世界首领</button><button className={sourceType==="delve"?"active":""} onClick={()=>{setSourceType("delve");setItemLevel(321)}}>地下堡</button></div><label>具体副本<select value={instance} onChange={event=>setInstance(event.target.value)}><option value="">所有副本</option>{instances.map(value=><option value={value.name_zh_cn} key={`${value.source_type}-${value.name_zh_cn}`}>{value.name_zh_cn}</option>)}</select></label><label>装备部位<select value={slot} onChange={event=>setSlot(event.target.value)}><option value="">所有部位</option>{Object.entries(slotNames).map(([key,name])=><option value={key} key={key}>{name}</option>)}</select></label><label>副属性组合</label><div className="stat-toggles">{Object.entries(statNames).map(([key,name])=><button className={selectedStats.includes(key)?"active":""} onClick={()=>toggleStat(key)} key={key}>{name}</button>)}</div><label className="switch-row"><span>仅看特效装备</span><input type="checkbox" checked={special} onChange={event=>setSpecial(event.target.checked)}/></label><button className="apply-filter" onClick={search}>应用筛选</button><small>符合条件：{items.length} 件</small></aside>
    <section className="loot-list app-panel"><header><div><h2>装备列表</h2><span>{loading?"正在读取…":`${items.length} 件装备`}</span></div><div>{selectedStats.map(value=><em key={value}>{statNames[value as StatKey]}</em>)}</div></header><div className="loot-head"><span>装备</span><span>装等</span><span>部位</span><span>属性</span><span>来源 / Boss</span><span>标签</span><span>操作</span></div><div className="loot-body">{items.map(item=>{const source=item.sources[0];return <article className="loot-row" key={item.item_id}><div className="loot-name"><a href={item.wowhead_url} data-wowhead={item.wowhead_data} target="_blank" rel="noreferrer"><img src={item.icon_url||""} alt=""/></a><span><a className="epic" href={item.wowhead_url} data-wowhead={item.wowhead_data} target="_blank" rel="noreferrer">{item.name_zh_cn}</a><small>{item.name_en}</small></span></div><b>{item.item_level}</b><span>{slotNames[itemSlot(item)]||itemSlot(item)}</span><div className="loot-stats">{(Object.entries(item.stats) as [StatKey,number][]).filter(([,value])=>value).map(([key,value])=><span className={statColors[key]} key={key}>{statNames[key]} <b>{value}</b></span>)}</div><span className="loot-source">{source?.instance_name_zh_cn||"制造"}<small>{source?.encounter_name_zh_cn}</small></span><div className="loot-tags">{item.has_special_effect&&<em>特效</em>}{item.catalyst_eligible&&<em>可转化</em>}{item.is_crafted&&<em>制造</em>}</div><button onClick={()=>addToBuilder(item)}>加入配装</button></article>})}</div></section>
  </div></main>;
}

export default function App() {
  const specs=useSpecs();const [path,setPath]=useState(location.pathname);
  const go=(next:string)=>{history.pushState({},"",next);setPath(next)};
  useEffect(()=>{const change=()=>setPath(location.pathname);addEventListener("popstate",change);return()=>removeEventListener("popstate",change)},[]);
  return <><header className="site-header"><a className="brand" href="/builder" onClick={event=>{event.preventDefault();go("/builder")}}><span>◆</span><div><b>艾泽拉斯配装助手</b><small>智能配装 · 数据驱动 · 版本 12.1</small></div></a><nav><a className={path!=="/loot"?"active":""} href="/builder" onClick={event=>{event.preventDefault();go("/builder")}}>AI智能配装</a><a className={path==="/loot"?"active":""} href="/loot" onClick={event=>{event.preventDefault();go("/loot")}}>装备数据库</a><span>刷本推荐</span><span>我的方案</span></nav><div className="header-meta"><b>12.1 赛季</b><span>✓ 数据已同步</span><em>Broo</em></div></header>{path==="/loot"?<LootPage specs={specs}/>:<BuilderPage specs={specs}/>}</>;
}
