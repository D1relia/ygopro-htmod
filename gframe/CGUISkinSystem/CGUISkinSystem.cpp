#include "CGUISkinSystem.h"

namespace {
class ScopedWorkingDirectory {
public:
	ScopedWorkingDirectory(io::IFileSystem* fs) : fs(fs), oldpath(fs->getWorkingDirectory()) {}
	~ScopedWorkingDirectory() {
		fs->changeWorkingDirectoryTo(oldpath);
	}

private:
	io::IFileSystem* fs;
	io::path oldpath;
};
}

CGUISkinSystem::CGUISkinSystem(core::string<wchar_t> path,IrrlichtDevice *dev) {
	device = dev;
	skinsPath = path;
	fs = dev->getFileSystem();	
	this->loadSkinList();
	
	
}
core::array<core::stringw> CGUISkinSystem::listSkins() {
	return skinsList;
}
// This is our version of the skinloader

// Generate a list of all directory names in skinsPath that have a skin.xml in them
// Don't rely on working directory going in.
// Careful with changeworkingdirectoryto and relative paths,
// remember that they are relative to the CURRENT working directory
bool CGUISkinSystem::loadSkinList() {
	io::IFileList *fileList;
	int i;
	ScopedWorkingDirectory cwd(fs);
	if(!fs->changeWorkingDirectoryTo(skinsPath))
		return false;
	fileList = fs->createFileList();
	i = fileList->getFileCount();
	core::stringw tmp;
	while(i--) {
		// Check only directories, skip . and ..
		// Side effect, on linux this ignores hidden directories
		if(fileList->isDirectory(i) && !fileList->getFileName(i).equalsn(".",1)) {
			if(fs->existFile(fileList->getFileName(i) + SKINSYSTEM_SKINFILE)) {
				tmp = fileList->getFileName(i);
				skinsList.push_back(tmp);						
			}
			
		}
	}	
	fileList->drop();
	if(skinsList.size() > 0) 
		return true;
	else 
		return false;
}
gui::CGUIProgressBar *CGUISkinSystem::addProgressBar(gui::IGUIElement *parent,core::rect<s32> rect, bool bindColorsToSkin) {
	gui::CGUIProgressBar* bar = new gui::CGUIProgressBar(parent,device->getGUIEnvironment(), rect,bindColorsToSkin);
	//gui::CImageGUISkin* skin = (gui::CImageGUISkin*)device->getGUIEnvironment()->getSkin();
	parent->addChild(bar);    
	bar->drop();
	return bar;
}


bool CGUISkinSystem::populateTreeView(gui::IGUITreeView *control,const core::stringc& skinname) {
	bool ret = false;
	ScopedWorkingDirectory cwd(fs);
	if(!fs->changeWorkingDirectoryTo(skinsPath))
		return ret;
	registry = new CXMLRegistry(fs);	
	if(!registry->loadFile(SKINSYSTEM_SKINFILE,skinname.c_str())) {
		delete registry;
		registry = NULL;
		return ret;
	}
	ret = registry->populateTreeView(control);
	delete registry;
	registry = NULL;
	return ret;
}

void CGUISkinSystem::ParseGUIElementStyle(gui::SImageGUIElementStyle& elem, const core::stringc& name, bool nullcolors) {
	core::stringw context;
	core::stringc ctmp,err = "";
	context = L"Skin/"; 
	context += name;
	core::rect<u32> box;
	video::SColor col;
	ctmp = registry->getValueAsCStr(L"texture",context.c_str());
	if(!ctmp.size()) 
		err += "Could not load texture property from skin file";	
	
	elem.Texture = device->getVideoDriver()->getTexture(ctmp);	
	
	box = registry->getValueAsRect((context + "/SrcBorder").c_str());
	elem.SrcBorder.Top = box.UpperLeftCorner.X;
	elem.SrcBorder.Left = box.UpperLeftCorner.Y;
	elem.SrcBorder.Bottom = box.LowerRightCorner.X;
	elem.SrcBorder.Right = box.LowerRightCorner.Y;
	
	box = registry->getValueAsRect((context + "/DstBorder").c_str());
	elem.DstBorder.Top = box.UpperLeftCorner.X;
	elem.DstBorder.Left = box.UpperLeftCorner.Y;
	elem.DstBorder.Bottom = box.LowerRightCorner.X;
	elem.DstBorder.Right = box.LowerRightCorner.Y;	
	if(nullcolors)
		elem.Color = video::SColor(0);
	col = registry->getValueAsColor((context +"/Color").c_str());
	if(col != video::SColor(0))
		elem.Color = col;
	else {
		col = registry->getValueAsColor((context +"/Colour").c_str());
		if(col != video::SColor(0))
			elem.Color = col;
	}
}

// Because my 'xmlloader/registry', already has the data access components
// We skip the 'configreader and skinloader' steps and just load right from the registry into the skin config
// Then create the skin from that, and set it up
// TO maintain compatability in case of upgrades
// We dont touch the iterface to the skin itself.

gui::CImageGUISkin* CGUISkinSystem::loadSkinFromFile(const c8 *skinname) {	
	gui::CImageGUISkin* skin ;
	gui::SImageGUISkinConfig skinConfig;
	gui::EGUI_SKIN_TYPE fallbackType;
	gui::IGUISkin *fallbackSkin;
	
	s32 i,x;
	core::stringc tmp;
	core::stringw wtmp;
	core::stringc path = "./";
	path += skinname;
	if(!registry->loadFile(SKINSYSTEM_SKINFILE,path.c_str())) {
		return NULL;
	}	
	// Easiest way to see if an xml is loading correctly
	// is to make the registry write out the root node and see what comes out.
	//registry->writeFile("Skin",".");
	
	// To switch on the fly, we have to set the skin to the fallback skin first	
	tmp = registry->getValueAsCStr(L"skin",L"Skin/Properties/Fallback");
	// Always default to metalic
	fallbackType = gui::EGST_WINDOWS_METALLIC;
	if(tmp.equals_ignore_case("EGST_WINDOWS_CLASSIC"))
		fallbackType = gui::EGST_WINDOWS_CLASSIC;
	else if(tmp.equals_ignore_case("EGST_BURNING_SKIN"))
		fallbackType = gui::EGST_BURNING_SKIN;	
	// I'm not dealing with the 'unknown skin'
	fallbackSkin = device->getGUIEnvironment()->createSkin(fallbackType);
	device->getGUIEnvironment()->setSkin(fallbackSkin);
	fallbackSkin->drop();

	skin = new gui::CImageGUISkin(device->getVideoDriver(), device->getGUIEnvironment()->getSkin());
	fs->changeWorkingDirectoryTo(path.c_str());
	ParseGUIElementStyle(skinConfig.Button,"Button");
	ParseGUIElementStyle(skinConfig.ButtonPressed, "Button/Pressed");
	ParseGUIElementStyle(skinConfig.ButtonDisabled, "Button/ButtonDisabled");
    ParseGUIElementStyle(skinConfig.SunkenPane, "SunkenPane");
    ParseGUIElementStyle(skinConfig.Window, "Window");
    ParseGUIElementStyle(skinConfig.ProgressBar, "ProgressBar",true);
    ParseGUIElementStyle(skinConfig.ProgressBarFilled, "ProgressBar/Filled",true);
	ParseGUIElementStyle(skinConfig.TabBody,"TabControl");
	ParseGUIElementStyle(skinConfig.TabButton,"TabControl/TabButton");
	ParseGUIElementStyle(skinConfig.TabButtonPressed,"TabControl/TabButtonPressed");
	ParseGUIElementStyle(skinConfig.MenuBar,"MenuBar");
	ParseGUIElementStyle(skinConfig.MenuPane,"MenuBar/MenuPane");
	ParseGUIElementStyle(skinConfig.MenuPressed,"MenuBar/MenuPressed");
	ParseGUIElementStyle(skinConfig.CheckBox,"CheckBox");
	ParseGUIElementStyle(skinConfig.CheckBoxDisabled,"CheckBox/CheckBoxDisabled");
	ParseGUIElementStyle(skinConfig.ComboBox,"ComboBox");
	ParseGUIElementStyle(skinConfig.ComboBoxDisabled,"ComboBox/ComboBoxDisabled");

	skinConfig.CheckBoxColor = registry->getValueAsColor(L"Skin/Global/CheckBoxColor");
	
	// If there was no progress bar colors set, set them in the config to the defaults
	// otherwise their 0,0,0,0. This is neccicary for the old klagui.	

	if(skinConfig.ProgressBar.Color == video::SColor(0))
		skinConfig.ProgressBar.Color = video::SColor();	
	if(skinConfig.ProgressBarFilled.Color == video::SColor(0))
		skinConfig.ProgressBarFilled.Color = video::SColor(255,255,0,0);

	// Load in the Info
	loadProperty((core::stringw)L"Name",skin);
	loadProperty((core::stringw)L"Author",skin);
	loadProperty((core::stringw)L"Version",skin);
	loadProperty((core::stringw)L"Date",skin);
	loadProperty((core::stringw)L"Desc",skin);
	skin->loadConfig(skinConfig);
	
	tmp = registry->getValueAsCStr(L"texture",L"Skin/Properties/Font");
	gui::IGUIFont *font = device->getGUIEnvironment()->getFont(tmp.c_str());
	if(font !=0) {
		device->getGUIEnvironment()->getSkin()->setFont(font, gui::EGDF_DEFAULT);
		device->getGUIEnvironment()->getSkin()->setFont(font, gui::EGDF_WINDOW);
	}
	// Get and set global alpha, problem with this, you can't set it to 0
	// He does this to make ALL the default stuff completly transparent
	// This has the downside that it whipes out things like checkbox and window button colors
	video::SColor newCol = video::SColor();
	video::SColor oldCol = newCol;
	x = registry->getValueAsInt(L"guialpha",L"Skin/Global/");
	if(x != 0) {
		i = gui::EGDC_COUNT;
		while(i--) {
			oldCol = skin->getColor((gui::EGUI_DEFAULT_COLOR)i);		
			
			newCol = oldCol;
			newCol.setAlpha(x);

			skin->setColor((gui::EGUI_DEFAULT_COLOR)i, newCol);	
		}
	}
	checkSkinColor(gui::EGDC_3D_DARK_SHADOW,L"Skin/Global/EGDC_32_DARK_SHADOW",skin);
	checkSkinColor(gui::EGDC_3D_SHADOW,L"Skin/Global/EGDC_3D_SHADOW",skin);
	checkSkinColor(gui::EGDC_3D_FACE,L"Skin/Global/EGDC_3D_FACE",skin);	
	checkSkinColor(gui::EGDC_3D_HIGH_LIGHT,L"Skin/Global/EGDC_3D_HIGH_LIGHT",skin);
	checkSkinColor(gui::EGDC_3D_LIGHT,L"Skin/Global/EGDC_3D_LIGHT",skin);
	checkSkinColor(gui::EGDC_ACTIVE_BORDER,L"Skin/Global/EGDC_ACTIVE_BORDER",skin);
	checkSkinColor(gui::EGDC_ACTIVE_CAPTION,L"Skin/Global/EGDC_ACTIVE_CAPTION",skin);
	checkSkinColor(gui::EGDC_APP_WORKSPACE,L"Skin/Global/EGDC_APP_WORKSPACE",skin);
	checkSkinColor(gui::EGDC_BUTTON_TEXT,L"Skin/Global/EGDC_BUTTON_TEXT",skin);
	checkSkinColor(gui::EGDC_GRAY_TEXT,L"Skin/Global/EGDC_GRAY_TEXT",skin);
	checkSkinColor(gui::EGDC_HIGH_LIGHT_TEXT,L"Skin/Global/EGDC_HIGH_LIGHT_TEXT",skin);
	checkSkinColor(gui::EGDC_INACTIVE_BORDER,L"Skin/Global/EGDC_INACTIVE_BORDER",skin);
	checkSkinColor(gui::EGDC_INACTIVE_CAPTION,L"Skin/Global/EGDC_INACTIVE_CAPTION",skin);
	checkSkinColor(gui::EGDC_TOOLTIP,L"Skin/Global/EGDC_TOOLTIP",skin);
	checkSkinColor(gui::EGDC_TOOLTIP_BACKGROUND,L"Skin/Global/EGDC_TOOLTIP_BACKGROUND",skin);
	checkSkinColor(gui::EGDC_SCROLLBAR,L"Skin/Global/EGDC_SCROLLBAR",skin);
	checkSkinColor(gui::EGDC_WINDOW,L"Skin/Global/EGDC_WINDOW",skin);
	checkSkinColor(gui::EGDC_WINDOW_SYMBOL,L"Skin/Global/EGDC_WINDOW_SYMBOL",skin);
	checkSkinColor(gui::EGDC_ICON,L"Skin/Global/EGDC_ICON",skin);	
	checkSkinColor(gui::EGDC_ICON_HIGH_LIGHT,L"Skin/Global/EGDC_ICON_HIGH_LIGHT",skin);
	
	
	
	checkSkinSize(gui::EGDS_WINDOW_BUTTON_WIDTH, L"Skin/Global/WindowButton",L"width",skin);	
	checkSkinSize(gui::EGDS_TITLEBARTEXT_DISTANCE_X, L"Skin/Global/Caption",L"tbardistancex",skin);
	checkSkinSize(gui::EGDS_TITLEBARTEXT_DISTANCE_Y, L"Skin/Global/Caption",L"tbardistancey",skin);
	

	return skin;
}
core:: stringw CGUISkinSystem::getProperty(core::stringw key) {
	gui::CImageGUISkin* skin = (gui::CImageGUISkin*)device->getGUIEnvironment()->getSkin();
	return skin->getProperty(key);
}

bool CGUISkinSystem::checkSkinColor(gui::EGUI_DEFAULT_COLOR colToSet,const wchar_t *context,gui::CImageGUISkin *skin) {
	video::SColor col = registry->getValueAsColor(context);
	if(col != video::SColor(0)) {
		skin->setColor(colToSet,col);
		return true;
	}
	return false;
}

bool CGUISkinSystem::checkSkinSize(gui::EGUI_DEFAULT_SIZE sizeToSet,const wchar_t *context,const wchar_t *key,gui::CImageGUISkin *skin) {
	u16 i = registry->getValueAsInt(key,context);
	if(i != 0) {
		skin->setSize(sizeToSet,i);
		return true;
	}
	return false;
}

bool CGUISkinSystem::loadProperty(core::stringw key,gui::CImageGUISkin *skin) {
	core::stringw wtmp = "Skin/Properties/";
	wtmp += key;
	wtmp = registry->getValueAsCStr(L"data",wtmp.c_str());
	if(wtmp.size()) {
		skin->setProperty(key,wtmp);
		return true;
	}
	return false;
}
bool CGUISkinSystem::applySkin(const wchar_t *skinname) {
	ScopedWorkingDirectory cwd(fs);
	core::stringc tmp = skinname;
	if(!fs->changeWorkingDirectoryTo(skinsPath))
		return false;
	registry = new CXMLRegistry(fs);
	gui::CImageGUISkin* skin = loadSkinFromFile(tmp.c_str());
    if(skin == NULL) {
		delete registry;
		registry = NULL;
		return false;
	}
	
    device->getGUIEnvironment()->setSkin(skin);
	// If we're going to switch skin we need to find all the progress bars and overwrite their colors	
    skin->drop();	
	delete registry;
	registry = NULL;
	
	return true;
}
CGUISkinSystem::~CGUISkinSystem() {
	skinsList.clear();
	

	
}
#include <IGUICheckBox.h>
#include <ICursorControl.h>
#include <cmath>
#include <algorithm>

namespace irr {
namespace gui {

CModernLightSkin::CModernLightSkin(IrrlichtDevice* device, IGUISkin* fallbackSkin)
	: Device(device), VideoDriver(device->getVideoDriver()), FallbackSkin(fallbackSkin) {
	if(FallbackSkin)
		FallbackSkin->grab();
	setColor(EGDC_3D_DARK_SHADOW,      video::SColor(255,  15,  23,  42));
	setColor(EGDC_3D_SHADOW,           video::SColor(255,  51,  65,  85));
	setColor(EGDC_3D_FACE,             video::SColor(242,  30,  41,  59));
	setColor(EGDC_3D_HIGH_LIGHT,       video::SColor(255,  71,  85, 105));
	setColor(EGDC_3D_LIGHT,            video::SColor(255,  38,  49,  68));
	setColor(EGDC_ACTIVE_BORDER,       video::SColor(220,  64,  80, 104));
	setColor(EGDC_INACTIVE_BORDER,     video::SColor(180,  51,  65,  85));
	setColor(EGDC_ACTIVE_CAPTION,      video::SColor(255, 241, 245, 249));
	setColor(EGDC_INACTIVE_CAPTION,    video::SColor(255, 148, 163, 184));
	setColor(EGDC_APP_WORKSPACE,       video::SColor(238,  22,  30,  44));
	setColor(EGDC_WINDOW,              video::SColor(238,  22,  30,  44));
	setColor(EGDC_BUTTON_TEXT,         video::SColor(255, 236, 241, 248));
	setColor(EGDC_GRAY_TEXT,           video::SColor(255, 100, 116, 139));
	setColor(EGDC_HIGH_LIGHT,          video::SColor(255,  10, 132, 255));
	setColor(EGDC_HIGH_LIGHT_TEXT,     video::SColor(255, 255, 255, 255));
	setColor(EGDC_TOOLTIP,             video::SColor(255, 241, 245, 249));
	setColor(EGDC_TOOLTIP_BACKGROUND,  video::SColor(245,  30,  41,  59));
	setColor(EGDC_SCROLLBAR,           video::SColor(110,  15,  23,  42));
	setColor(EGDC_WINDOW_SYMBOL,       video::SColor(255, 203, 213, 225));
	setColor(EGDC_ICON,                video::SColor(255, 203, 213, 225));
	setColor(EGDC_ICON_HIGH_LIGHT,     video::SColor(255, 255, 255, 255));
	setSize(EGDS_TITLEBARTEXT_DISTANCE_X, 12);
	setSize(EGDS_TITLEBARTEXT_DISTANCE_Y, 2);
}

CModernLightSkin::~CModernLightSkin() {
	if(FallbackSkin)
		FallbackSkin->drop();
}

video::SColor CModernLightSkin::getColor(EGUI_DEFAULT_COLOR color) const { return FallbackSkin->getColor(color); }
void CModernLightSkin::setColor(EGUI_DEFAULT_COLOR which, video::SColor newColor) { FallbackSkin->setColor(which, newColor); }
s32 CModernLightSkin::getSize(EGUI_DEFAULT_SIZE size) const { return FallbackSkin->getSize(size); }
const wchar_t* CModernLightSkin::getDefaultText(EGUI_DEFAULT_TEXT text) const { return FallbackSkin->getDefaultText(text); }
void CModernLightSkin::setDefaultText(EGUI_DEFAULT_TEXT which, const wchar_t* newText) { FallbackSkin->setDefaultText(which, newText); }
void CModernLightSkin::setSize(EGUI_DEFAULT_SIZE which, s32 size) { FallbackSkin->setSize(which, size); }
IGUIFont* CModernLightSkin::getFont(EGUI_DEFAULT_FONT defaultFont) const { return FallbackSkin->getFont(defaultFont); }
void CModernLightSkin::setFont(IGUIFont* font, EGUI_DEFAULT_FONT defaultFont) { FallbackSkin->setFont(font, defaultFont); }
IGUISpriteBank* CModernLightSkin::getSpriteBank() const { return FallbackSkin->getSpriteBank(); }
void CModernLightSkin::setSpriteBank(IGUISpriteBank* bank) { FallbackSkin->setSpriteBank(bank); }
u32 CModernLightSkin::getIcon(EGUI_DEFAULT_ICON icon) const { return FallbackSkin->getIcon(icon); }
void CModernLightSkin::setIcon(EGUI_DEFAULT_ICON icon, u32 index) { FallbackSkin->setIcon(icon, index); }

bool CModernLightSkin::isHovered(IGUIElement* element, const core::rect<s32>& rect, const core::rect<s32>* clip) const {
	if(!element || !element->isEnabled() || !Device)
		return false;
	IGUIEnvironment* env = Device->getGUIEnvironment();
	if(!env)
		return false;
	IGUIElement* hovered = env->getHovered();
	if(!hovered)
		return false;
	// 标签栏的多个页签共用同一个 IGUITabControl 指针，跳过以免同时全部点亮
	if(element->getType() == EGUIET_TAB_CONTROL)
		return false;
	return hovered == element;
}

void CModernLightSkin::drawRoundedBox(const core::rect<s32>& rect, s32 radius, video::SColor fill, video::SColor border, const core::rect<s32>* clip, bool fillBg) const {
	s32 w = rect.getWidth();
	s32 h = rect.getHeight();
	if(w <= 0 || h <= 0)
		return;
	s32 r = std::min(radius, std::min(w / 2, h / 2));
	bool hasBorder = (border.getAlpha() > 0);
	bool hasFill = (fillBg && fill.getAlpha() > 0);
	s32 x1 = rect.UpperLeftCorner.X;
	s32 y1 = rect.UpperLeftCorner.Y;
	s32 x2 = rect.LowerRightCorner.X;
	s32 y2 = rect.LowerRightCorner.Y;

	if(r <= 1) {
		if(hasFill) {
			s32 b = hasBorder ? 1 : 0;
			VideoDriver->draw2DRectangle(fill, core::rect<s32>(x1 + b, y1 + b, x2 - b, y2 - b), clip);
		}
		if(hasBorder) {
			VideoDriver->draw2DRectangle(border, core::rect<s32>(x1, y1, x2, y1 + 1), clip);
			VideoDriver->draw2DRectangle(border, core::rect<s32>(x1, y2 - 1, x2, y2), clip);
			VideoDriver->draw2DRectangle(border, core::rect<s32>(x1, y1 + 1, x1 + 1, y2 - 1), clip);
			VideoDriver->draw2DRectangle(border, core::rect<s32>(x2 - 1, y1 + 1, x2, y2 - 1), clip);
		}
		return;
	}

	float rf = static_cast<float>(r);
	float inRf = static_cast<float>(r - 1);
	for(s32 i = 0; i < r; ++i) {
		float dy = (rf - 0.5f) - static_cast<float>(i);
		s32 outX = static_cast<s32>(std::floor(rf - std::sqrt(std::max(0.0f, rf * rf - dy * dy)) + 0.5f));
		s32 rowTop = y1 + i;
		s32 rowBot = y2 - 1 - i;

		if(!hasBorder) {
			if(hasFill && x1 + outX < x2 - outX) {
				VideoDriver->draw2DRectangle(fill, core::rect<s32>(x1 + outX, rowTop, x2 - outX, rowTop + 1), clip);
				if(rowBot != rowTop)
					VideoDriver->draw2DRectangle(fill, core::rect<s32>(x1 + outX, rowBot, x2 - outX, rowBot + 1), clip);
			}
		} else if(i == 0 || dy >= inRf) {
			if(x1 + outX < x2 - outX) {
				VideoDriver->draw2DRectangle(border, core::rect<s32>(x1 + outX, rowTop, x2 - outX, rowTop + 1), clip);
				if(rowBot != rowTop)
					VideoDriver->draw2DRectangle(border, core::rect<s32>(x1 + outX, rowBot, x2 - outX, rowBot + 1), clip);
			}
		} else {
			s32 inX = static_cast<s32>(std::floor(rf - std::sqrt(std::max(0.0f, inRf * inRf - dy * dy)) + 0.5f));
			if(inX <= outX) inX = outX + 1;
			VideoDriver->draw2DRectangle(border, core::rect<s32>(x1 + outX, rowTop, x1 + inX, rowTop + 1), clip);
			VideoDriver->draw2DRectangle(border, core::rect<s32>(x2 - inX, rowTop, x2 - outX, rowTop + 1), clip);
			if(rowBot != rowTop) {
				VideoDriver->draw2DRectangle(border, core::rect<s32>(x1 + outX, rowBot, x1 + inX, rowBot + 1), clip);
				VideoDriver->draw2DRectangle(border, core::rect<s32>(x2 - inX, rowBot, x2 - outX, rowBot + 1), clip);
			}
			if(hasFill && x1 + inX < x2 - inX) {
				VideoDriver->draw2DRectangle(fill, core::rect<s32>(x1 + inX, rowTop, x2 - inX, rowTop + 1), clip);
				if(rowBot != rowTop)
					VideoDriver->draw2DRectangle(fill, core::rect<s32>(x1 + inX, rowBot, x2 - inX, rowBot + 1), clip);
			}
		}
	}

	if(y1 + r < y2 - r) {
		if(hasFill) {
			s32 b = hasBorder ? 1 : 0;
			VideoDriver->draw2DRectangle(fill, core::rect<s32>(x1 + b, y1 + r, x2 - b, y2 - r), clip);
		}
		if(hasBorder) {
			VideoDriver->draw2DRectangle(border, core::rect<s32>(x1, y1 + r, x1 + 1, y2 - r), clip);
			VideoDriver->draw2DRectangle(border, core::rect<s32>(x2 - 1, y1 + r, x2, y2 - r), clip);
		}
	}
}

void CModernLightSkin::drawSoftShadow(const core::rect<s32>& rect, s32 radius, const core::rect<s32>* clip) const {
	for(s32 i = 3; i >= 1; --i) {
		core::rect<s32> sr(
			rect.UpperLeftCorner.X - i,
			rect.UpperLeftCorner.Y - i + 2,
			rect.LowerRightCorner.X + i,
			rect.LowerRightCorner.Y + i + 2);
		u32 alpha = static_cast<u32>(36 - i * 8);
		drawRoundedBox(sr, radius + i, video::SColor(alpha, 2, 6, 16), video::SColor(0, 0, 0, 0), clip, true);
	}
}

void CModernLightSkin::draw3DButtonPaneStandard(IGUIElement* element, const core::rect<s32>& rect, const core::rect<s32>* clip) {
	bool hov = isHovered(element, rect, clip);
	if(element && element->getType() == EGUIET_SCROLL_BAR) {
		core::rect<s32> thumb = rect;
		s32 pad = 2;
		if(rect.getWidth() > rect.getHeight()) {
			thumb.UpperLeftCorner.Y += pad;
			thumb.LowerRightCorner.Y -= pad;
		} else {
			thumb.UpperLeftCorner.X += pad;
			thumb.LowerRightCorner.X -= pad;
		}
		s32 rad = std::min(thumb.getWidth(), thumb.getHeight()) / 2;
		video::SColor col = hov ? video::SColor(235, 100, 116, 139) : video::SColor(185, 71, 85, 105);
		drawRoundedBox(thumb, rad, col, video::SColor(0, 0, 0, 0), clip, true);
		return;
	}
	if(element && element->isSubElement() && element->getParent()) {
		auto ptype = element->getParent()->getType();
		if(ptype == EGUIET_SCROLL_BAR) {
			if(hov) {
				core::rect<s32> r = rect;
				r.UpperLeftCorner.X += 1; r.UpperLeftCorner.Y += 1;
				r.LowerRightCorner.X -= 1; r.LowerRightCorner.Y -= 1;
				drawRoundedBox(r, 4, video::SColor(180, 51, 65, 85), video::SColor(0, 0, 0, 0), clip, true);
			}
			return;
		}
		if(ptype == EGUIET_COMBO_BOX) {
			core::rect<s32> r = rect;
			r.UpperLeftCorner.Y += 1; r.LowerRightCorner.Y -= 1; r.LowerRightCorner.X -= 1;
			video::SColor bg = hov ? video::SColor(235, 36, 52, 77) : video::SColor(0, 0, 0, 0);
			drawRoundedBox(r, 5, bg, video::SColor(0, 0, 0, 0), clip, hov);
			return;
		}
		if(ptype == EGUIET_WINDOW) {
			if(hov) {
				drawRoundedBox(rect, 5, video::SColor(235, 127, 29, 29), video::SColor(255, 248, 113, 113), clip, true);
			}
			return;
		}
	}

	core::rect<s32> r = rect;
	if(r.getWidth() > 26 && r.getHeight() > 16) {
		r.UpperLeftCorner.X += 1;
		r.UpperLeftCorner.Y += 1;
		r.LowerRightCorner.X -= 1;
		r.LowerRightCorner.Y -= 1;
	}
	s32 rad = std::min<s32>(7, r.getHeight() / 3);
	if(rad < 4) rad = 4;

	if(element && !element->isEnabled()) {
		drawRoundedBox(r, rad, video::SColor(175, 26, 33, 46), video::SColor(135, 51, 65, 85), clip, true);
		return;
	}
	core::rect<s32> sh = r;
	sh.UpperLeftCorner.Y += 1;
	sh.LowerRightCorner.Y += 1;
	drawRoundedBox(sh, rad, video::SColor(45, 2, 6, 16), video::SColor(0, 0, 0, 0), clip, true);

	s32 elemId = element ? element->getID() : -1;
	if(elemId >= 240 && elemId <= 249) {
		video::SColor accent(255, 148, 163, 184);
		video::SColor bgNorm(244, 24, 32, 46);
		video::SColor bgHov(252, 40, 52, 74);
		switch(elemId) {
		case 240: // 发动
			accent = video::SColor(255, 245, 158, 11);
			bgNorm = video::SColor(244, 48, 36, 18);
			bgHov  = video::SColor(252, 82, 56, 18);
			break;
		case 241: // 通常召唤
			accent = video::SColor(255, 56, 189, 248);
			bgNorm = video::SColor(244, 18, 38, 56);
			bgHov  = video::SColor(252, 22, 62, 92);
			break;
		case 242: // 特殊召唤
			accent = video::SColor(255, 129, 140, 248);
			bgNorm = video::SColor(244, 28, 30, 60);
			bgHov  = video::SColor(252, 46, 48, 98);
			break;
		case 243: // 盖放怪兽
		case 244: // 盖放魔陷
			accent = video::SColor(255, 52, 211, 153);
			bgNorm = video::SColor(244, 16, 42, 36);
			bgHov  = video::SColor(252, 22, 68, 56);
			break;
		case 245: // 变更表示形式
			accent = video::SColor(255, 192, 132, 252);
			bgNorm = video::SColor(244, 38, 26, 56);
			bgHov  = video::SColor(252, 62, 38, 92);
			break;
		case 246: // 攻击宣言
			accent = video::SColor(255, 248, 113, 113);
			bgNorm = video::SColor(244, 54, 22, 26);
			bgHov  = video::SColor(252, 92, 30, 34);
			break;
		}
		drawRoundedBox(r, rad, hov ? bgHov : bgNorm, accent, clip, true);
		core::rect<s32> inner(r.UpperLeftCorner.X + 1, r.UpperLeftCorner.Y + 1, r.LowerRightCorner.X - 1, r.LowerRightCorner.Y - 1);
		drawRoundedBox(inner, std::max<s32>(2, rad - 1), video::SColor(0, 0, 0, 0), video::SColor(hov ? 220 : 150, accent.getRed(), accent.getGreen(), accent.getBlue()), clip, false);
		return;
	}

	if(hov) {
		drawRoundedBox(r, rad, video::SColor(250, 30, 56, 92), video::SColor(255, 10, 132, 255), clip, true);
	} else {
		drawRoundedBox(r, rad, video::SColor(242, 35, 45, 63), video::SColor(210, 64, 79, 104), clip, true);
	}
}

void CModernLightSkin::draw3DButtonPanePressed(IGUIElement* element, const core::rect<s32>& rect, const core::rect<s32>* clip) {
	if(element && element->getType() == EGUIET_SCROLL_BAR) {
		s32 rad = std::min(rect.getWidth(), rect.getHeight()) / 2;
		drawRoundedBox(rect, rad, video::SColor(245, 148, 163, 184), video::SColor(0, 0, 0, 0), clip, true);
		return;
	}
	core::rect<s32> r = rect;
	if(r.getWidth() > 26 && r.getHeight() > 16) {
		r.UpperLeftCorner.X += 1;
		r.UpperLeftCorner.Y += 1;
		r.LowerRightCorner.X -= 1;
		r.LowerRightCorner.Y -= 1;
	}
	s32 rad = std::min<s32>(7, r.getHeight() / 3);
	if(rad < 4) rad = 4;
	drawRoundedBox(r, rad, video::SColor(255, 10, 102, 204), video::SColor(255, 56, 189, 248), clip, true);
}

void CModernLightSkin::draw3DSunkenPane(IGUIElement* element, video::SColor bgcolor, bool flat, bool fillBackGround, const core::rect<s32>& rect, const core::rect<s32>* clip) {
	bool hov = isHovered(element, rect, clip);
	bool focused = (element && Device && Device->getGUIEnvironment() && Device->getGUIEnvironment()->hasFocus(element));
	if(element && element->getType() == EGUIET_CHECK_BOX) {
		bool checked = static_cast<IGUICheckBox*>(element)->isChecked();
		if(checked) {
			video::SColor blue = hov ? video::SColor(255, 48, 154, 255) : video::SColor(255, 10, 132, 255);
			drawRoundedBox(rect, 5, blue, blue, clip, true);
		} else {
			video::SColor bd = hov ? video::SColor(255, 10, 132, 255) : video::SColor(220, 82, 98, 122);
			drawRoundedBox(rect, 5, video::SColor(245, 17, 23, 35), bd, clip, true);
		}
		return;
	}
	if(element && element->getType() == EGUIET_STATIC_TEXT) {
		bool drawPillFill = fillBackGround || (rect.getHeight() < 80);
		video::SColor bg = drawPillFill ? video::SColor(220, 32, 43, 61) : video::SColor(0, 0, 0, 0);
		video::SColor bd = drawPillFill ? video::SColor(0, 0, 0, 0) : video::SColor(180, 56, 72, 98);
		drawRoundedBox(rect, drawPillFill ? 6 : 10, bg, bd, clip, drawPillFill);
		return;
	}
	video::SColor fill = (element && !element->isEnabled())
		? video::SColor(190, 20, 27, 40)
		: video::SColor(248, 15, 21, 33);
	video::SColor border = focused
		? video::SColor(255, 10, 132, 255)
		: (hov ? video::SColor(235, 100, 116, 139) : video::SColor(200, 56, 70, 94));
	drawRoundedBox(rect, 6, fill, border, clip, fillBackGround);
}

core::rect<s32> CModernLightSkin::draw3DWindowBackground(IGUIElement* element, bool drawTitleBar, video::SColor titleBarColor, const core::rect<s32>& rect, const core::rect<s32>* clip, core::rect<s32>* checkClientArea) {
	s32 barH = getSize(EGDS_WINDOW_BUTTON_WIDTH) + 8;
	if(checkClientArea) {
		*checkClientArea = rect;
		checkClientArea->UpperLeftCorner.X += 1;
		checkClientArea->LowerRightCorner.X -= 1;
		checkClientArea->LowerRightCorner.Y -= 1;
		if(drawTitleBar)
			checkClientArea->UpperLeftCorner.Y += barH + 1;
		else
			checkClientArea->UpperLeftCorner.Y += 1;
		return *checkClientArea;
	}
	drawSoftShadow(rect, 10, clip);
	drawRoundedBox(rect, 10, video::SColor(238, 24, 32, 46), video::SColor(210, 56, 70, 94), clip, true);
	core::rect<s32> titleRect = rect;
	if(drawTitleBar) {
		VideoDriver->draw2DRectangle(video::SColor(180, 51, 65, 85), core::rect<s32>(rect.UpperLeftCorner.X + 10, rect.UpperLeftCorner.Y + barH, rect.LowerRightCorner.X - 10, rect.UpperLeftCorner.Y + barH + 1), clip);
		titleRect.UpperLeftCorner.X += 10;
		titleRect.UpperLeftCorner.Y += 2;
		titleRect.LowerRightCorner.X -= 6;
		titleRect.LowerRightCorner.Y = rect.UpperLeftCorner.Y + barH;
	}
	return titleRect;
}

void CModernLightSkin::draw3DMenuPane(IGUIElement* element, const core::rect<s32>& rect, const core::rect<s32>* clip) {
	drawSoftShadow(rect, 8, clip);
	drawRoundedBox(rect, 8, video::SColor(250, 26, 35, 50), video::SColor(220, 64, 79, 104), clip, true);
}

void CModernLightSkin::draw3DToolBar(IGUIElement* element, const core::rect<s32>& rect, const core::rect<s32>* clip) {
	drawRoundedBox(rect, 8, video::SColor(238, 24, 32, 46), video::SColor(200, 56, 70, 94), clip, true);
}

void CModernLightSkin::draw3DTabButton(IGUIElement* element, bool active, const core::rect<s32>& rect, const core::rect<s32>* clip, EGUI_ALIGNMENT alignment) {
	bool hov = isHovered(element, rect, clip);
	core::rect<s32> r = rect;
	r.UpperLeftCorner.X += 2;
	r.LowerRightCorner.X -= 2;
	r.UpperLeftCorner.Y += 2;
	r.LowerRightCorner.Y -= 2;
	if(active) {
		core::rect<s32> sh = r;
		sh.UpperLeftCorner.Y += 1; sh.LowerRightCorner.Y += 1;
		drawRoundedBox(sh, 6, video::SColor(40, 2, 6, 16), video::SColor(0, 0, 0, 0), clip, true);
		drawRoundedBox(r, 6, video::SColor(250, 35, 46, 65), video::SColor(210, 64, 79, 104), clip, true);
		s32 padX = std::max<s32>(6, r.getWidth() / 5);
		if(r.UpperLeftCorner.X + padX < r.LowerRightCorner.X - padX) {
			s32 barY = (alignment == EGUIA_UPPERLEFT) ? (r.LowerRightCorner.Y - 3) : (r.UpperLeftCorner.Y + 1);
			VideoDriver->draw2DRectangle(video::SColor(255, 10, 132, 255), core::rect<s32>(r.UpperLeftCorner.X + padX, barY, r.LowerRightCorner.X - padX, barY + 2), clip);
		}
	} else {
		video::SColor bg = hov ? video::SColor(220, 30, 40, 58) : video::SColor(155, 20, 27, 40);
		drawRoundedBox(r, 6, bg, video::SColor(0, 0, 0, 0), clip, true);
	}
}

void CModernLightSkin::draw3DTabBody(IGUIElement* element, bool border, bool background, const core::rect<s32>& rect, const core::rect<s32>* clip, s32 tabHeight, gui::EGUI_ALIGNMENT alignment) {
	core::rect<s32> body = rect;
	if(tabHeight == -1)
		tabHeight = getSize(EGDS_BUTTON_HEIGHT);
	if(alignment == EGUIA_UPPERLEFT)
		body.UpperLeftCorner.Y += tabHeight + 2;
	else
		body.LowerRightCorner.Y -= tabHeight + 2;
	drawSoftShadow(body, 10, clip);
	drawRoundedBox(body, 10, video::SColor(238, 24, 32, 46), border ? video::SColor(210, 56, 70, 94) : video::SColor(0, 0, 0, 0), clip, background);
}

void CModernLightSkin::drawIcon(IGUIElement* element, EGUI_DEFAULT_ICON icon, const core::position2di position, u32 starttime, u32 currenttime, bool loop, const core::rect<s32>* clip) {
	if(icon == EGDI_CHECK_BOX_CHECKED) {
		if(clip && !clip->isPointInside(position))
			return;
		s32 s = getSize(EGDS_CHECK_BOX_WIDTH) / 4;
		if(s < 3) s = 3;
		core::position2di p1(position.X - s, position.Y);
		core::position2di p2(position.X - s / 3, position.Y + s - 1);
		core::position2di p3(position.X + s + 1, position.Y - s + 1);
		video::SColor white(255, 255, 255, 255);
		VideoDriver->draw2DLine(p1, p2, white);
		VideoDriver->draw2DLine(p2, p3, white);
		VideoDriver->draw2DLine(core::position2di(p1.X, p1.Y - 1), core::position2di(p2.X, p2.Y - 1), white);
		VideoDriver->draw2DLine(core::position2di(p2.X, p2.Y - 1), core::position2di(p3.X, p3.Y - 1), white);
		return;
	}
	FallbackSkin->drawIcon(element, icon, position, starttime, currenttime, loop, clip);
}

void CModernLightSkin::draw2DRectangle(IGUIElement* element, const video::SColor& color, const core::rect<s32>& pos, const core::rect<s32>* clip) {
	if(element && element->getType() == EGUIET_STATIC_TEXT) {
		drawSoftShadow(pos, 10, clip);
		drawRoundedBox(pos, 8, video::SColor(244, 22, 30, 46), video::SColor(220, 71, 85, 105), clip, true);
		return;
	}
	VideoDriver->draw2DRectangle(color, pos, clip);
}

}
}
