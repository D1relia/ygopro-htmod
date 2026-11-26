import io
import json
import re
import shutil
import sqlite3
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

# ================= 配置区域 =================
YGOPRO_DIR = Path(".")
SOURCE_CDB = YGOPRO_DIR / "cards.cdb"
SOURCE_STRINGS = YGOPRO_DIR / "strings.conf"
BACKUP_STRINGS = YGOPRO_DIR / "strings.conf.bak"
EXTERNAL_SETNAME_FILE = YGOPRO_DIR / "setname.txt"

OUTPUT_DIR = YGOPRO_DIR / "expansions"
OUTPUT_CDB = OUTPUT_DIR / "sc_official.cdb"
OUTPUT_STRINGS = OUTPUT_DIR / "strings.conf"

YGOCDB_ZIP_URL = "https://ygocdb.com/api/v0/cards.zip"

# 内置人工校对版 setname 字段表（最高优先级）
BUILTIN_SETNAME_TEXT = """#setnames, using tab for comment
!setname 0x1 正义盟军\tA・O・J
!setname 0x2 次代机\tジェネクス
!setname 0x1002 真次代机\tレアル·ジェネクス
#!setname 0x2002 盟军·次代机\tA・ジェネクス
!setname 0x3 魅惑女王\t魅惑の女王
!setname 0x4 亚马逊\tアマゾネス
!setname 0x5 秘仪之力\tアルカナフォース
!setname 0x6 暗黑界\t暗黒界
!setname 0x7 古代机械齿轮\tアンティーク・ギア
!setname 0x8 英雄\tHERO
!setname 0x3008 元素－英雄\tE・HERO
!setname 0x5008 幻影－英雄\tV・HERO
!setname 0x6008 邪心－英雄\tE-HERO
!setname 0xa008 假面－英雄\tM・HERO
!setname 0xc008 命运－英雄\tD-HERO
!setname 0x9 新宇侠\tネオス
!setname 0xa 邪蚀\tヴェルズ
!setname 0x100a 侵邪蚀\tインヴェルズ
!setname 0xb 无限狱\tインフェルニティ
!setname 0xc 外星人\tエーリアン
!setname 0xd 军刀\tセイバー
!setname 0x100d X-军刀\tX－セイバー
#setname 0x300d XX-军刀\tXX－セイバー
!setname 0x400d 元素军刀\tエレメントセイバー
!setname 0xe 电力\tエレキ
!setname 0xf 扰乱怪\tおジャマ
!setname 0x10 薰风\tガスタ
!setname 0x11 机偶\tカラクリ
!setname 0x12 青蛙\tガエル
!setname 0x13 机皇\t機皇
!setname 0x3013 机皇帝\t機皇帝
!setname 0x5013 机皇神\t機皇神
!setname 0x6013 机皇兵\t機皇兵
#setname 0x14 N/A
!setname 0x15 巨大战舰\t巨大戦艦
!setname 0x16 机人\tロイド
!setname 0x1016 超级交通机人\tビークロイド
!setname 0x2016 疾行机人\tスピードロイド
!setname 0x17 同步\tシンクロ
!setname 0x1017 同步士\tシンクロン
!setname 0x2017 同步龙\tシンクロ・ドラゴン
!setname 0x18 云魔物\t雲魔物
!setname 0x19 剑斗兽\tグラディアル
!setname 0x1019 剑斗兽\t剣闘獣
!setname 0x1a 黑蝎\t黒蠍
!setname 0x1b 幻兽\t幻獣
!setname 0x101b 幻兽机\t幻獣機
!setname 0x1c 死之信息\t死のメッセージ
!setname 0x1d 核成\tコアキメイル
!setname 0x1e 茧状体\tC（コクーン）
!setname 0x1f 新空间人\tN（ネオスペーシアン）
!setname 0x20 紫炎\t紫炎
!setname 0x21 地缚\t地縛
!setname 0x1021 地缚神\t地縛神
!setname 0x22 朱罗纪\tジュラック
!setname 0x23 罪\tSin
!setname 0x24 废铁\tスクラップ
!setname 0x25 链条\tC（チェーン）
!setname 0x26 变形斗士\tD（ディフォーマー）
!setname 0x27 T.G.\tTG（テックジーナス）
!setname 0x28 电池人\t電池メン
!setname 0x29 龙骑兵团\tドラグニティ
!setname 0x2a 大植然\tナチュル
!setname 0x2b 忍者
!setname 0x2c 炎狱\tフレムベル
#setname 0x2d N/A
!setname 0x2e 守墓\t墓守
!setname 0x2f 冰结界\t氷結界
!setname 0x30 大日神械\tヴァイロン
!setname 0x31 命运女郎\tフォーチュンレディ
!setname 0x32 火山性\tヴォルカニック
!setname 0x33 黑羽\tBF（ブラックフェザー）
!setname 0x1033 强袭黑羽\tA BF（アサルト ブラックフェザー）
!setname 0x34 宝玉\t宝玉
!setname 0x1034 宝玉兽\t宝玉獣
!setname 0x2034 究极宝玉神\t究極宝玉神
!setname 0x5034 高等宝玉兽\tA宝玉獣
!setname 0x35 魔轰神\t魔轟神
!setname 0x36 机甲部队\tマシンナーズ
!setname 0x37 霞之谷\t霞の谷
!setname 0x38 光道\tライトロード
!setname 0x39 岩浆炎\tラヴァル
!setname 0x3a 咒仪\tリチュア
!setname 0x3b 真红眼\tレッドアイズ
!setname 0x3c 爬虫妖\tレプティレス
#setname 0x3d 六武
!setname 0x103d 六武众\t六武衆
!setname 0x203d 六武式
#setname 0x503d 真六武众\t真六武衆
!setname 0x903d 影六武众\t影六武衆
!setname 0x3e 异虫\tワーム
!setname 0x3f 救世\tセイヴァー
!setname 0x40 被封印者\t封印されし
!setname 0x41 LV\tLV（レベル）
!setname 0x42 极星\t極星
!setname 0x3042 极星天\t極星天
!setname 0x5042 极星宝\t極星宝
!setname 0x6042 极星兽\t極星獣
!setname 0xa042 极星灵\t極星霊
!setname 0x43 废品\tジャンク
!setname 0x44 代行者
!setname 0x45 恶魔\tデーモン
!setname 0x1045 红恶魔\tレッド・デーモン
!setname 0x46 结合\t融合/フュージョン
!setname 0x1046 结合龙\tフュージョン・ドラゴン
!setname 0x47 宝石\tジェム
!setname 0x1047 宝石骑士\tジェムナイト
!setname 0x48 编号\tNo.（ナンバーズ）
!setname 0x1048 混沌编号\tCNo.
!setname 0x2048 编号99
!setname 0x49 铳士\t銃士
!setname 0x4a 时械神\t時械神
!setname 0x4b 极神\t極神
!setname 0x4c 落穴\t落とし穴
#setname 0x4d N/A
#setname 0x4e 进化\tエヴォル
!setname 0x304e 进化虫\tエヴォルド
!setname 0x504e 进化帝\tエヴォルカイザー
!setname 0x604e 进化龙\tエヴォルダー
#setname 0x4f 爆裂\tバスター
!setname 0x104f ／爆裂\t／バスター
!setname 0x50 猛毒\tヴェノム
!setname 0x1050 凶饿猛毒\tスターヴ・ヴェノム
!setname 0x51 小工具\tガジェット
!setname 0x52 守护者\tガーディアン
!setname 0x1052 门之守护者|守护者\tゲート・ガーディアン
!setname 0x2052 法理守护者\tローガーディアン
!setname 0x53 星圣\tセイクリッド
!setname 0x54 我我我\tガガガ
!setname 0x55 光子\tフォトン
!setname 0x56 甲虫装机\t甲虫装機
!setname 0x57 共鸣者\tリゾネーター
!setname 0x58 发条\tゼンマイ
!setname 0x59 隆隆隆\tゴゴゴ
!setname 0x5a 企鹅\tペンギン
!setname 0x5b 番茄仔\tトマボー
!setname 0x5c 斯芬克斯\tスフィンクス
#setname 0x5d N/A
#setname 0x5e N/A
#setname 0x5f N/A
!setname 0x60 竹光
!setname 0x61 忍法
!setname 0x62 卡通\tトゥーン
!setname 0x63 热核\tリアクター
!setname 0x64 神鹰\tハーピィ
!setname 0x65 侵略的\t侵略の
!setname 0x66 战士\tウォリアー
!setname 0x1066 音响战士\t音響戦士
!setname 0x2066 磁石战士\tマグネット・ウォリアー
!setname 0x6066 磁石战士西格玛\t磁石の戦士Σ
#setname 0x67 钢铁\tアイアン
#setname 0x68 铁皮\tブリキ
!setname 0x69 圣刻\t聖刻
!setname 0x6a 幻蝶刺客\t幻蝶の刺客
!setname 0x6b 豹镖\tバウンサー
#setname 0x6c 光芒使者\tライトレイ
!setname 0x6d 魔者\t魔人（まじん）
!setname 0x6e 魔导\t魔導
!setname 0x106e 魔导书\t魔導書
!setname 0x6f 英豪\tヒロイック
!setname 0x106f 英豪挑战者\tH・C
!setname 0x206f 英豪胜利者\tH－C
!setname 0x70 先史遗产\t先史遺産
!setname 0x71 魔幻甜点\tマドルチェ
!setname 0x72 齿轮齿轮\tギアギア
!setname 0x1072 齿轮齿轮人\tギアギアーノ
!setname 0x73 超量\tエクシーズ
!setname 0x1073 混沌超量\tCX（カオスエクシーズ）
!setname 0x2073 超量龙\tエクシーズ・ドラゴン
!setname 0x4073 装甲超量\tアーマード・エクシーズ
!setname 0x74 水精鳞\t水精鱗
!setname 0x75 邃渊\tアビス
!setname 0x76 纹章兽\t紋章獣
!setname 0x77 海皇
!setname 0x78 迅捷\t素早い
!setname 0x79 炎星
#setname 0x7a 圣\t聖
!setname 0x107a 圣骑士\t聖騎士（せいきし）
!setname 0x207a 圣剑\t聖剣（せいけん）
!setname 0x507a 焰圣骑士\t焔聖騎士
!setname 0x607a 焰圣剑\t焔聖剣
!setname 0x7b 银河\tギャラクシー
!setname 0x107b 银河眼\tギャラクシーアイズ
!setname 0x307b 银河眼时空龙\tギャラクシーアイズ・タキオン・ドラゴン
!setname 0x7c 炎舞
!setname 0x7d 阳炎\tヘイズ
!setname 0x107d 阳炎兽\t陽炎獣
!setname 0x7e ZEXAL\tゼアル
!setname 0x107e ZEXAL兵器\tZW（ゼアル・ウェポン）
!setname 0x207e ZEXAL从者\tZS（ゼアル・サーバス）
!setname 0x7f 霍普\tホープ
!setname 0x107f 希望皇霍普\t希望皇ホープ
!setname 0x207f 未来皇霍普\t未来皇ホープ
!setname 0x80 尘小妖\tダストン
!setname 0x81 炎王
!setname 0x1081 炎王兽\t炎王獣
!setname 0x82 怒怒怒\tドドド
!setname 0x83 傀偶\tパペット
!setname 0x1083 机关傀偶\tギミック・パペット
#setname 0x84 燃烧拳\tバーニングナック
!setname 0x1084 燃烧拳斗士\tBK（バーニングナックラー）
!setname 0x2084 燃烧拳击\tバーニングナックル
!setname 0x85 超防卫机器人\tSDロボ
!setname 0x86 辉天使
!setname 0x87 黑影\tアンブラル
!setname 0x88 武斗神
!setname 0x89 空洞\tホール
#setname 0x8a 虫惑\t蟲惑
!setname 0x108a 虫惑魔\t蟲惑魔
!setname 0x8b 噬恶\tマリスボラス
#setname 0x8c 德鲁伊\tドルイド
!setname 0x8d 鬼计\tゴーストリック
!setname 0x8e 吸血鬼\tヴァンパイア
!setname 0x8f 刷拉拉\tズババ
!setname 0x90 森罗\t森羅
!setname 0x91 死灵谷\tネクロバレー
!setname 0x92 徽章\tメダリオン
!setname 0x93 电子\tサイバー
!setname 0x1093 电子龙\tサイバー・ドラゴン
!setname 0x2093 电子天使\tサイバー・エンジェル
!setname 0x4093 电子暗黑\tサイバー・ダーク/サイバーダーク
!setname 0x94 人工脑\tサイバネティック
!setname 0x95 升阶魔法\tRUM
!setname 0x96 鱼博格\tフィッシュボーグ
!setname 0x97 古遗物\tアーティファクト
!setname 0x98 魔术师\t魔術師
!setname 0x99 异色眼\tオッドアイズ
!setname 0x9a 超重武者
!setname 0x109a 超重武者装魂
!setname 0x9b 幻奏
!setname 0x109b 幻奏音姬\t幻奏の音姫
!setname 0x9c 星骑士\tテラナイト
!setname 0x109c 辉星骑士\tステラナイト
!setname 0x9d 影依\tシャドール
!setname 0x9e 龙星\t竜星
!setname 0x9f 娱乐伙伴\tEM（エンタメイト）
!setname 0xa0 传说骑士\t伝説の騎士
!setname 0xa1 传说之龙\t伝説の竜
#setname 0xa2 魔术士\tマジシャン
!setname 0x10a2 黑魔导\tブラック・マジシャン
!setname 0x20a2 魔导女孩\tマジシャン・ガール
!setname 0x30a2 黑魔导女孩\tブラック・マジシャン・ガール
!setname 0xa3 星尘\tスターダスト
!setname 0xa4 库里波\tクリボー
!setname 0x10a4 羽翼库里波\tハネクリボー
!setname 0xa5 变换\tチェンジ
!setname 0xa6 幼芽\tスプラウト
!setname 0xa7 阿托利斯\tアルトリウス
!setname 0xa8 兰斯洛特\tランスロット
!setname 0xa9 绒毛动物\tファーニマル
!setname 0xaa 机壳\tクリフォート
!setname 0x10aa 隐藏的机壳\tアポクリフォート
!setname 0xab 文具博格\tブンボーグ
!setname 0xac 格布林\tゴブリン
!setname 0x10ac 格布林百罗刹\tゴブリンライダー
!setname 0xad 魔玩具\tデストーイ
!setname 0xae 契约书\t契約書
!setname 0xaf DD
!setname 0x10af DDD
!setname 0xb0 加特姆士\tガトムズ
!setname 0xb1 彼岸恶鬼
!setname 0xb2 超级运动员\tU.A.
!setname 0xb3 妖仙兽\t妖仙獣
!setname 0xb4 影灵衣\t影霊衣
!setname 0xb5 灵兽\t霊獣
!setname 0x10b5 灵兽使\t霊獣使い
!setname 0x20b5 精灵兽\t精霊獣
#!setname 0x30b5 精灵兽使\t精霊獣使い
!setname 0x40b5 圣灵兽骑\t聖霊獣騎
!setname 0xb6 外神
!setname 0xb7 旧神
!setname 0xb8 古神
!setname 0xb9 烈焰加农炮\tブレイズ・キャノン
!setname 0xba 急袭猛禽\tRR（レイド・ラプターズ）
!setname 0xbb 狱炎机\tインフェルノイド
!setname 0xbc 人造人\t人造人間
!setname 0xbd 暗黑骑士盖亚\t暗黒騎士ガイア
!setname 0xbe 帝王\t帝王
!setname 0xbf 灵使\t霊使い
!setname 0xc0 凭依\t憑依
!setname 0x10c0 凭依装着\t憑依装着
!setname 0xc1 精神骨架\tPSYフレーム
!setname 0x10c1 精神骨架装备\tPSYフレームギア
!setname 0xc2 动力工具\tパワー・ツール
!setname 0xc3 锋利小鬼\tエッジインプ
!setname 0xc4 源质\tセフィラ
!setname 0xc5 炼狱\t煉獄
!setname 0xc6 娱乐巫师\tEm（エンタメイジ）
!setname 0xc7 龙剑士\t竜剣士
!setname 0xc8 点火骑士\tイグナイト
!setname 0xc9 芬芳\tアロマ
!setname 0xca 魔装战士\t魔装戦士
!setname 0xcb 以太兵器\tイーサルウェポン
!setname 0xcc 占卜姬\t占術姫
!setname 0xcd 水伶女\tアクアアクトレス
!setname 0xce 水剧台\tアクアリウム
!setname 0xcf 混沌\tカオス
!setname 0x10cf 混沌士兵\tカオス・ソルジャー
!setname 0xd0 威风魔灵\tマジェスペクター
!setname 0xd1 灰篮\tグレイドル
!setname 0xd2 星际仙踪\tKozmo
!setname 0xd3 坏兽\t壊獣
!setname 0xd4 伯吉斯吸虫\tバージェストマ
!setname 0xd5 但丁\tダンテ
!setname 0xd6 破坏剑\t破壊剣
!setname 0xd7 毁灭剑士\tバスター・ブレイダー
!setname 0xd8 机动雾龙\tダイナミスト
!setname 0xd9 不知火
!setname 0x10d9 妖刀-不知火\t妖刀－不知火
!setname 0xda 龙魔王\t竜魔王
!setname 0xdb 魅影\tファントム
!setname 0x10db 魅影骑士团\t幻影騎士団
!setname 0xdc 超级量子\t超量
!setname 0x10dc 超级量子士\t超量士
!setname 0x20dc 超级量子机兽\t超量機獣
!setname 0xdd 青眼\tブルーアイズ
!setname 0xde 艾克佐迪亚\tエクゾディア
!setname 0xdf 月光\tムーンライト
!setname 0xe0 无形噬体\tアモルファージ
!setname 0xe1 炼装\tメタルフォーゼ
!setname 0xe2 三形金字塔\tトラミッド
!setname 0xe3 方界
!setname 0xe4 精灵剑士\tエルフの剣士
!setname 0xe5 光波\tサイファー
!setname 0x10e5 光波龙\tサイファー・ドラゴン
!setname 0xe6 花札卫\t花札衛
!setname 0xe7 沉默剑士\tサイレント・ソードマン
!setname 0xe8 沉默魔术师\tサイレント・マジシャン
!setname 0xe9 磁石战士\t磁石の戦士(じしゃくのせんし)
!setname 0xea 水晶机巧|非「机巧」\tクリストロン
!setname 0xeb 化合兽\t化合獣
#!setname 0xec\t魔界\t魔界
!setname 0x10ec 魔界剧团\t魔界劇団
!setname 0x20ec 魔界剧本 \t魔界台本
!setname 0xed 地中骇界\tサブテラー
!setname 0x10ed 地中骇界邪龙\tサブテラーマリス
!setname 0xee 秘旋谍\tSPYRAL
!setname 0x10ee 秘旋谍装备\tSPYRAL GEAR
!setname 0x20ee 秘旋谍任务\tSPYRAL MISSION
!setname 0xef 堕天使
!setname 0xf0 风魔女\tWW（ウィンド・ウィッチ）
!setname 0xf1 十二兽\t十二獣
!setname 0xf2 灵摆\tペンデュラム
!setname 0x10f2 灵摆龙\tペンデュラム・ドラゴン
!setname 0x20f2 灵摆读阵\tペンデュラムグラフ
!setname 0xf3 捕食者\tプレデター
!setname 0x10f3 捕食植植
!setname 0xf4 召唤兽\t召喚獣
!setname 0xf5 钢多拉\tガンドラ
!setname 0xf6 摩天楼
!setname 0xf7 抒情歌鸲\tLL（リリカル・ルスキニア）
#!setname 0xf8 霸王\t覇王
!setname 0x10f8 霸王门\t覇王門
!setname 0x20f8 霸王眷龙\t覇王眷竜
!setname 0xf9 真龙\t真竜
!setname 0xfa 幻煌龙\t幻煌龍
!setname 0xfb 淘气仙星\tトリックスター
!setname 0xfc 刚鬼\t剛鬼
!setname 0xfd 星杯龙
!setname 0xfe 星遗物\t星遺物
!setname 0xff 清透翼\tクリアウィング
!setname 0x100 键结\tボンディング
!setname 0x101 码语者\tコード・トーカー
!setname 0x102 枪弹\tヴァレット
!setname 0x103 幻变骚灵\tオルターガイスト
!setname 0x104 机怪虫\tクローラー
!setname 0x105 玄化\tメタファイズ
!setname 0x106 仇尸\tヴェンデット
!setname 0x107 方程式运动员\tF.A.
!setname 0x108 魔弹\t魔弾
!setname 0x109 天气\t天気
!setname 0x10a 珀耳修斯\tパーシアス
!setname 0x10b 廷达三角\tティンダングル
!setname 0x10c 机界骑士\tジャックナイツ
!setname 0x10d 魔导兽|非「魔导」\t魔導獣
!setname 0x10e 进化药\t進化薬
!setname 0x10f 枪管\tヴァレル
!setname 0x110 纳祭\tサクリファイス
!setname 0x1110 眼纳祭魔\tアイズ・サクリファイス
!setname 0x111 武装龙\tアームド・ドラゴン
!setname 0x112 梦魇曲\tトロイメア
!setname 0x113 灵神\t霊神
!setname 0x114 空牙团\t空牙団
!setname 0x115 闪刀\t閃刀
!setname 0x1115 闪刀姬\t閃刀姫
!setname 0x116 圣骑联盟\tパラディオン
!setname 0x117 魔神仪\t魔神儀
!setname 0x118 电脑网\tサイバネット
!setname 0x119 转生炎兽\tサラマングレイト
!setname 0x11a 恐龙摔跤手\tダイナレスラー
!setname 0x11b 自鸣天琴\tオルフェゴール
!setname 0x11c 雷龙\tサンダー·ドラゴン
!setname 0x11d 禁忌的\t禁じられた
!setname 0x11e 未界域
!setname 0x11f 奈芙蒂斯\tネフティス
!setname 0x120 调皮宝贝\tプランキッズ
!setname 0x121 魔妖
!setname 0x122 女武神|非「武神」\tワルキューレ
!setname 0x123 蔷薇\tローズ
!setname 0x1123 蔷薇龙\tローズ・ドラゴン
!setname 0x124 机械天使\t機械天使
!setname 0x125 微笑\tスマイル
!setname 0x126 时潜怪盗\tクロノダイバー
!setname 0x127 无限起动\t無限起動
!setname 0x128 魔女工艺\tウィッチクラフト
!setname 0x129 咒眼\t呪眼
!setname 0x12a 恩底弥翁\tエンディミオン
!setname 0x12b 海晶少女\tマリンセス
!setname 0x12c 天威龙
!setname 0x12d 西摩格\tシムルグ
!setname 0x12e 占卜魔女\t占い魔女
!setname 0x12f 蜂军\tB・F（ビー・フォース）
!setname 0x130 破械
!setname 0x1130 破械神
!setname 0x131 梦魔镜\t夢魔鏡
!setname 0x132 斩机\t斬機
!setname 0x133 龙女仆\tドラゴンメイド
!setname 0x134 创王\tジェネレイド
!setname 0x135 ＠伊格尼斯者\t@イグニスター
!setname 0x136 -艾-\tAi（アイ）
!setname 0x137 战华\t戦華
!setname 0x138 巨石异物\tメガリス
!setname 0x139 守护神官\t守護神官
!setname 0x13a 拟声\tオノマト
!setname 0x13b 反叛\tリベリオン
!setname 0x13c 码破者\tコードブレイカー
!setname 0x13d 星义\tネメシス
!setname 0x13e 巴巴罗斯\tバルバロス
!setname 0x13f 海造贼\t海造賊
!setname 0x140 魔救\tアダマシア
!setname 0x141 六花
#setname 0x142 黄金国\tエルド
!setname 0x1142 埃尔德里奇\tエルドリッチ
!setname 0x2142 埃尔德里希尔\tエルドリクシル
!setname 0x143 黄金乡\t黄金郷
!setname 0x144 幻魔
!setname 0x1144 三幻魔
!setname 0x145 教导\tドラグマ
!setname 0x146 梅尔菲\tメルフィー
!setname 0x147 波坦\tポータン
!setname 0x148 罗兰\tローラン
!setname 0x149 生代化石
!setname 0x14a 源数\tヌメロン
!setname 0x114a 源数之门\tゲート・オブ・ヌメロン
!setname 0x14b 机块\t機塊
#setname 0x14c 灵术\t霊術
!setname 0x314c 地灵术\t地霊術
!setname 0x514c 水灵术\t水霊術
!setname 0x614c 火灵术\t火霊術
!setname 0x914c 风灵术\t風霊術
#setname 0xa14c 光灵术\t光霊術
#setname 0xc14c 暗灵术\t闇霊術
!setname 0x14d 铁兽\tトライブリゲード
!setname 0x14e 电脑堺\t電脳堺
!setname 0x114e 电脑堺门\t電脳堺門
!setname 0x14f 双天
!setname 0x150 伟魔\tマギストス
#setname 0x151 双子\tTwin
!setname 0x1151 直播☆双子\tLive☆Twin
!setname 0x2151 邪恶★双子\tEvil★Twin
!setname 0x152 姬丝吉尔\tキスキル
!setname 0x153 璃拉\tリィラ
!setname 0x154 龙仪巧\tドライトロン
!setname 0x155 守宝团\tスプリガンズ
!setname 0x156 超元特防队\tS－Force
!setname 0x157 突异变种\tミュートリア
#setname 0x158 圣\tサン
!setname 0x1158 圣蔓\tサンヴァイン
!setname 0x2158 圣天树\tサンアバロン
!setname 0x4158 圣种\tサンシード
!setname 0x159 圣夜骑士团\tホーリーナイツ
!setname 0x15a 人偶怪兽\tドール・モンスター
!setname 0x15b 惊乐园\tアメイズメント
!setname 0x15c 惊乐游乐设施\tアトラクション
!setname 0x15d 烙印
!setname 0x15e 降阶魔法\tRDM
!setname 0x15f 战吼\tウォークライ
!setname 0x160 原物质\tマテリアクトル
!setname 0x161 溟界
!setname 0x162 音服和弦\tドレミコード
!setname 0x1162 天籁音服和弦\tグランドレミコード
!setname 0x163 北斗天熊\tベアルクティ
!setname 0x164 惨绝戏\tデスピア
!setname 0x165 魔键\t魔鍵
!setname 0x166 军贯\t軍貫
!setname 0x1167 森之圣兽\t森の聖獣
!setname 0x2167 森之圣灵\t森の聖霊
!setname 0x168 隐形蜇拉肯\tステルス・クラーゲン
!setname 0x169 原数天灵\tヌメロニアス
!setname 0x16a 号数\tナンバーズ
!setname 0x16b 相剑\t相剣
!setname 0x16c 冰翡\t氷水
!setname 0x16d 随风飘飘游\tふわんだりぃず
!setname 0x16e 拓扑逻辑\tトポロジック
!setname 0x16f 许珀里翁\tヒュペリオン
!setname 0x170 骑甲虫\tビートルーパー
!setname 0x171 朋.克.\tP.U.N.K.
!setname 0x172 驱魔姐妹\tエクソシスター
!setname 0x173 恐啡肽骇龙\tダイノルフィア
!setname 0x174 恶之魔娘\t悪魔嬢
!setname 0x175 七皇\tセブンス
!setname 0x176 巴利安\tバリアンズ
!setname 0x177 利维坦\tリバイアサン
!setname 0x178 潜海奇袭\tシー・ステルス
!setname 0x179 兽带斗士\tセリオンズ
!setname 0x17a 恐惧爪\tスケアクロー
!setname 0x17b 野蛮人\tバーバリアン
!setname 0x17c 书灵师\tリブロマンサー
!setname 0x17d 弈勇\tヴァリアンツ
!setname 0x17e 拉比丽斯\tラビュリンス
!setname 0x117e 光临拉比丽斯\tウェルカム・ラビュリンス
!setname 0x17f 神碑
!setname 0x180 电光闪灵\tスプライト
!setname 0x181 泪冠哀歌\tティアラメンツ
!setname 0x182 春化精
!setname 0x183 悠悠\tもけもけ
!setname 0x184 翼人\tウィングマン
#setname 0x185 涂鸦\tらくがき
!setname 0x1185 涂yā兽\tらくがきじゅう
!setname 0x2185 涂yā本\tらくがきちょう
!setname 0x186 G魔像\tGゴーレム
!setname 0x187 桥梁\t架け橋
!setname 0x188 渊兽\tビーステッド
!setname 0x189 怒刹帝利\tクシャトリラ
!setname 0x18a 游魊\tゴーティス
!setname 0x18b 救援王牌\tR－ACE
!setname 0x18c 皮尔莉\tピュアリィ
!setname 0x18d 御巫
!setname 0x18e 仪水镜\t儀水鏡
!setname 0x18f 防火墙\tファイアウォール
!setname 0x190 玛那桃圆乡\tマナドゥム
!setname 0x191 妮梦雷莉娅\tネムレリア
!setname 0x192 黄金荣耀\tGP（ゴールド・プライド）
!setname 0x193 迷宫壁\tラビリンス・ウォール
!setname 0x194 至爱-英雄\tフェイバリット
!setname 0x195 对击斗魂\tVS（ヴァンキッシュ・ソウル）
!setname 0x196 饿魔新喰\tヌーベルズ
!setname 0x197 食谱\tレシピ
!setname 0x198 维萨思\tヴィサス
!setname 0x199 反击\tカウンター
!setname 0x19a 韦陀\tヴェーダ
!setname 0x19b 迪亚贝尔\tディアベル
!setname 0x119b 迪亚贝尔斯塔\tディアベルスター
!setname 0x19c 蛇眼\tスネークアイ
!setname 0x19d 荷鲁斯\tホルス
!setname 0x119d 荷鲁斯之黑炎龙\tホルスの黒炎竜
!setname 0x19e 罪宝
!setname 0x19f 圣果使\t聖菓使
!setname 0x1a0 哈忒\tハート
!setname 0x1a1 冥铭途\tメメント
!setname 0x1a2 百夫骑\tセンチュリオン
!setname 0x1a3 华耳琴璃\tヴァルモニカ
!setname 0x1a4 提斯蒂娜\tティスティナ
!setname 0x1a5 尤贝尔\tユベル
!setname 0x1a6 肃声\t粛声
!setname 0x1a7 白斗气\tホワイト・オーラ
!setname 0x1a8 玩具\tトイ
!setname 0x1a9 灿幻\t燦幻
!setname 0x1aa 天杯龙\t天盃龍
!setname 0x1ab 蕾祸\t蕾禍
!setname 0x1ac 沙罗曼龙\tサラマンドラ
!setname 0x1ad 灰灭\t灰滅
!setname 0x1ae 仟年\t千年/ミレニアム
!setname 0x1af 艾格佐德\tエグゾード
!setname 0x1b0 魔镌\tデモンスミス
!setname 0x1b1 白森\t白き森
!setname 0x1b2 多多迷宝\tマルチャミー
!setname 0x1b3 徽纹\tエンブレーマ
!setname 0x1b4 时空\tタキオン
!setname 0x1b5 青泪\t青い涙
!setname 0x1b6 石版
!setname 0x1b7 迷拟宝箱鬼\tミミグル
!setname 0x1b8 鲨\tシャーク
!setname 0x11b8 海咬龙 鲨龙兽\tシャーク・ドレイク
!setname 0x1b9 原石
!setname 0x1ba 钢铁化\tメタル化
!setname 0x1bb 绿柱魔瞳\tモルガナイト
!setname 0x1bc 圣徒\tアザミナ
!setname 0x1bd 祝台
!setname 0x1be 雷热涡炉\tライゼオル
!setname 0x1bf 码丽丝\tM∀LICE
!setname 0x1c0 龙华\t竜華
!setname 0x1c1 阿尔戈☆群星\tARG☆S
!setname 0x1c2 水波喷气机\tアクア・ジェット
!setname 0x1c3 巳剑\t巳剣
!setname 0x1c4 征龙\t征竜
!setname 0x1c5 再世\tリジェネシス
!setname 0x1c6 主王\tドミナス
!setname 0x31c6 圣王的粉碎\tドミナス・パージ
!setname 0x1c7 塞尔凯特\tセルケト
!setname 0x1c8 阿波菲斯\tアポピス
!setname 0x1c9 星宿\tドラゴンテイル
!setname 0x1ca 黯蜜\tヤミー
!setname 0x1cb K9
!setname 0x1cc 瞬移\tテレポート
!setname 0x1cd 神艺\tアルトメギア
!setname 0x1ce 狱神\t獄神
!setname 0x1cf R.B.\tR.B.
!setname 0x1d0 死伟王\t死偉王
!setname 0x1d1 绚岚\t絢嵐
!setname 0x1d2 终刻\tドゥームズ
!setname 0x1d3 百臂无形手\tヘカトンケイル
!setname 0x1d4 纠罪巧\t糾罪巧
!setname 0x1d5 杀手旋律\tキラーチューン
!setname 0x1d6 树袋熊\tコアラ
!setname 0x1d7 艾克利西亚\tエクレシア
!setname 0x1d8 耀圣\tエルフェンノーツ
!setname 0x1d9 磁石\tマグネット
!setname 0x1da 世界终灭\tエンド・オブ・ザ・ワールド
!setname 0x1db 妖精传姬\t妖精伝姫
!setname 0x1dc 小丑戏帮\t道化の一座
!setname 0x1dd GMX\tGMX
!setname 0x1de 黑暗协调\tDT
!setname 0x1df 雷盟\tブリッツクリーク
!setname 0x1e0 预幻\tテオリアライズ
!setname 0x1e1 阿莱斯特\tアレイスター
!setname 0x1e2 具象天使\tAngelechy
!setname 0x1e3 假面魔蹈士\t仮面魔踏士
!setname 0x1e4 艮鬼\tアシュトラ
!setname 0x1e5 代达罗斯\tダイダロス
!setname 0x1e6 奥艺\tアルス＝マグナ
!setname 0x1e7 迪亚克特罗斯\tディアクトロス
!setname 0x1e8 墨迪乌斯\tメディウス
!setname 0x1e9 白夜\tホワイトナイツ
!setname 0x1ea 列王
!setname 0x1eb 塞尼特\tセネト
!setname 0x1ec 盈彩月夜\tレイズ・ムーン
!setname 0x1ed 异解△\t異解△"""
# ===========================================


def parse_setname_line(line: str) -> tuple[int, str, str] | None:
    stripped = line.strip()
    if not stripped.startswith("!setname"):
        return None
    main_part = stripped.split("\t", 1)[0].strip()
    parts = main_part.split(None, 2)
    if len(parts) < 3:
        return None
    try:
        code = int(parts[1], 16)
    except ValueError:
        return None
    raw_name = parts[2].strip()
    clean_name = raw_name.split("|", 1)[0].strip()
    return code, clean_name, stripped


def load_curated_setnames() -> tuple[dict[int, str], dict[int, str], list[str]]:
    code_to_clean_name: dict[int, str] = {}
    code_to_full_line: dict[int, str] = {}

    source_text = BUILTIN_SETNAME_TEXT
    if EXTERNAL_SETNAME_FILE.exists():
        ext_text = EXTERNAL_SETNAME_FILE.read_text(encoding="utf-8-sig", errors="replace")
        if "!setname" in ext_text:
            source_text = source_text + "\n" + ext_text

    out_lines = [line.strip() for line in BUILTIN_SETNAME_TEXT.splitlines()]
    for line in source_text.splitlines():
        parsed = parse_setname_line(line)
        if parsed:
            code, clean_name, full_line = parsed
            code_to_clean_name[code] = clean_name
            code_to_full_line[code] = full_line

    return code_to_clean_name, code_to_full_line, out_lines


def prepare_strings_and_setmap() -> dict[str, str]:
    if BACKUP_STRINGS.exists():
        shutil.copy2(BACKUP_STRINGS, SOURCE_STRINGS)
        BACKUP_STRINGS.unlink()
        print("[3/5] 已将根目录下的 strings.conf 自动还原为初始原版。")

    code_to_new_clean, _, builtin_lines = load_curated_setnames()
    old_to_new_setname: dict[str, str] = {}

    if SOURCE_STRINGS.exists():
        orig_lines = SOURCE_STRINGS.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        for line in orig_lines:
            parsed = parse_setname_line(line)
            if parsed:
                code, old_clean_name, _ = parsed
                new_clean_name = code_to_new_clean.get(code)
                if new_clean_name and old_clean_name and old_clean_name != new_clean_name:
                    old_to_new_setname[old_clean_name] = new_clean_name

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if EXTERNAL_SETNAME_FILE.exists():
        ext_content = EXTERNAL_SETNAME_FILE.read_text(encoding="utf-8-sig", errors="replace")
        OUTPUT_STRINGS.write_text(ext_content, encoding="utf-8")
    else:
        OUTPUT_STRINGS.write_text("\n".join(builtin_lines) + "\n", encoding="utf-8")

    print(
        f"[3/5] 已生成 expansions/strings.conf（共内置 {len(code_to_new_clean)} 个字段，"
        f"精准对齐 {len(old_to_new_setname)} 组新旧不同译名）。"
    )
    return old_to_new_setname


def fetch_ygocdb_mapping() -> tuple[dict[int, str], dict[int, str], dict[str, str], dict[str, str]]:
    """分级提取百鸽数据：将 简中官译(sc) 与 大师决斗译名(md) 独立存储，避免 md 覆盖同组 sc"""
    print(f"[1/5] 正在从百鸽下载最新卡片数据包: {YGOCDB_ZIP_URL} ...")
    req = urllib.request.Request(
        YGOCDB_ZIP_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        zip_bytes = resp.read()

    print("[2/5] 正在内存中解压并解析 cards.json ...")
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        with zf.open("cards.json") as f:
            cards_data = json.load(f)

    id_to_sc: dict[int, str] = {}
    id_to_md: dict[int, str] = {}
    cn_to_sc: dict[str, str] = {}
    cn_to_md: dict[str, str] = {}

    for item in cards_data.values():
        text_obj = item.get("text", {}) if isinstance(item.get("text"), dict) else {}
        sc_val = (item.get("sc_name") or text_obj.get("sc_name") or "").strip()
        md_val = (item.get("md_name") or text_obj.get("md_name") or "").strip()
        cn_val = (item.get("cn_name") or text_obj.get("cn_name") or "").strip()

        card_id = item.get("id")
        if card_id:
            cid = int(card_id)
            if sc_val:
                id_to_sc[cid] = sc_val
            if md_val:
                id_to_md[cid] = md_val

        if cn_val:
            if sc_val and sc_val != cn_val:
                cn_to_sc[cn_val] = sc_val
            if md_val and md_val != cn_val:
                cn_to_md[cn_val] = md_val

    print(f"      共解析出 {len(id_to_sc)} 张简中官译(sc)、{len(id_to_md)} 张MD官译卡片。")
    return id_to_sc, id_to_md, cn_to_sc, cn_to_md


def is_same_card_variant(base_row: tuple, var_row: tuple) -> bool:
    """
    判定 alias 指向 base_row 的卡片是否为同一张卡的异画/超框版本
    （排除「传说之都 亚特兰蒂斯 -> 海」「鹰身女郎1 -> 鹰身女郎」等规则同名但实为不同卡的情况）
    """
    # row 结构: (id, alias, type, atk, def, level, race, attribute, name, desc)
    if base_row[2:8] != var_row[2:8]:
        return False
    var_desc = var_row[9] or ""
    base_desc = base_row[9] or ""
    if "规则上" in var_desc and "规则上" not in base_desc:
        return False
    return True


def update_single_cdb(
    cdb_path: Path,
    id_to_sc: dict[int, str],
    id_to_md: dict[int, str],
    cn_to_sc: dict[str, str],
    cn_to_md: dict[str, str],
    old_to_new_setname: dict[str, str],
) -> tuple[int, int]:
    conn = sqlite3.connect(cdb_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT d.id, d.alias, d.type, d.atk, d.def, d.level, d.race, d.attribute, t.name, t.desc
        FROM datas d
        JOIN texts t ON d.id = t.id
    """)
    rows = cursor.fetchall()

    row_by_id = {r[0]: r for r in rows}
    orig_id_to_name = {r[0]: (r[8] or "").strip() for r in rows}

    # 构建同名异画/超框卡组：base_id -> [base_id, variant_id_1, variant_id_2, ...]
    groups: dict[int, list[int]] = defaultdict(list)
    card_to_root: dict[int, int] = {}

    for r in rows:
        cid, alias = r[0], r[1]
        if alias and alias in row_by_id and is_same_card_variant(row_by_id[alias], r):
            root_id = alias
        else:
            root_id = cid
        card_to_root[cid] = root_id
        if cid not in groups[root_id]:
            groups[root_id].append(cid)
        if root_id not in groups[root_id]:
            groups[root_id].insert(0, root_id)

    old_to_new_card: dict[str, str] = {**cn_to_md, **cn_to_sc}
    resolved_names: dict[int, str] = {}

    # 对每个同名卡组按三级优先级统一决策译名
    for root_id, members in groups.items():
        base_old_name = orig_id_to_name.get(root_id, "")
        chosen_name = None

        # 优先级 1：组内任意卡命中百鸽简中官译 (sc_name)
        for m in members:
            m_old = orig_id_to_name.get(m, "")
            if m in id_to_sc:
                chosen_name = id_to_sc[m]
                break
            if m_old and m_old in cn_to_sc:
                chosen_name = cn_to_sc[m_old]
                break

        # 优先级 2：组内超框/异画卡在库中已自带不同于旧主卡的新译名（如超框版已录入「黑之魔导的帘布」）
        if not chosen_name and len(members) > 1:
            for m in members:
                if m != root_id:
                    var_name = orig_id_to_name.get(m, "")
                    if var_name and var_name != base_old_name:
                        chosen_name = var_name
                        break

        # 优先级 3：组内任意卡命中百鸽大师决斗官译 (md_name)
        if not chosen_name:
            for m in members:
                m_old = orig_id_to_name.get(m, "")
                if m in id_to_md:
                    chosen_name = id_to_md[m]
                    break
                if m_old and m_old in cn_to_md:
                    chosen_name = cn_to_md[m_old]
                    break

        if chosen_name:
            for m in members:
                resolved_names[m] = chosen_name
                m_old = orig_id_to_name.get(m, "")
                if m_old and m_old != chosen_name:
                    old_to_new_card[m_old] = chosen_name

    # 全局同名卡兜底同步
    for r in rows:
        cid = r[0]
        old_name = orig_id_to_name.get(cid, "")
        if cid not in resolved_names and old_name in old_to_new_card:
            resolved_names[cid] = old_to_new_card[old_name]

    combined_quote_map = {**old_to_new_card, **old_to_new_setname}
    quote_pattern = re.compile(r"「([^」]+)」")

    def replace_quoted(match: re.Match) -> str:
        inner = match.group(1)
        if inner in combined_quote_map:
            return f"「{combined_quote_map[inner]}」"
        return match.group(0)

    updates = []
    name_changed_count = 0
    desc_changed_count = 0

    for r in rows:
        card_id = r[0]
        old_name = r[8] or ""
        old_desc = r[9] or ""
        target_name = resolved_names.get(card_id, old_name)
        target_desc = old_desc

        if old_desc and "「" in old_desc:
            new_desc = quote_pattern.sub(replace_quoted, old_desc)
            if new_desc != old_desc:
                target_desc = new_desc
                desc_changed_count += 1

        if target_name != old_name:
            name_changed_count += 1

        if target_name != old_name or target_desc != old_desc:
            updates.append((target_name, target_desc, card_id))

    cursor.executemany("UPDATE texts SET name = ?, desc = ? WHERE id = ?", updates)
    conn.commit()

    # 打印 41350417 同组卡片的实时核验结果
    cursor.execute("SELECT d.id, d.alias, t.name FROM datas d JOIN texts t ON d.id = t.id WHERE d.id = 41350417 OR d.alias = 41350417")
    verify_rows = cursor.fetchall()
    if verify_rows:
        print(f"      [核验 {cdb_path.name}] 41350417 同组卡片当前译名:")
        for vid, valias, vname in verify_rows:
            print(f"        -> 卡密 {vid} (alias={valias}): {orig_id_to_name.get(vid)} ==> {vname}")

    conn.close()
    return name_changed_count, desc_changed_count


def convert_cdb(mapping_data: tuple) -> None:
    id_to_sc, id_to_md, cn_to_sc, cn_to_md = mapping_data

    if not SOURCE_CDB.exists():
        raise FileNotFoundError(f"未找到 {SOURCE_CDB.resolve()}")

    old_to_new_setname = prepare_strings_and_setmap()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_CDB, OUTPUT_CDB)

    print("[4/5] 正在按同名卡组三级优先级同步更新数据库 ...")
    name_cnt, desc_cnt = update_single_cdb(
        OUTPUT_CDB, id_to_sc, id_to_md, cn_to_sc, cn_to_md, old_to_new_setname
    )

    # 若 expansions 目录下还有其他独立 .cdb 扩展卡包，一并同步转换防止覆盖
    for extra_cdb in OUTPUT_DIR.glob("*.cdb"):
        if extra_cdb.resolve() != OUTPUT_CDB.resolve():
            print(f"      检测到扩展包数据库 {extra_cdb.name}，正在同步转换 ...")
            update_single_cdb(
                extra_cdb, id_to_sc, id_to_md, cn_to_sc, cn_to_md, old_to_new_setname
            )

    print("[5/5] 全部转换完成！")
    print(f"      - 更新卡片名称: {name_cnt} 张")
    print(f"      - 更新效果文本「卡名/字段」引用: {desc_cnt} 条")


if __name__ == "__main__":
    mapping = fetch_ygocdb_mapping()
    convert_cdb(mapping)