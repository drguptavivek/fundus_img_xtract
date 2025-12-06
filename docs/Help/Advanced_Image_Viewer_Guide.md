# Advanced Image Viewer Help Guide

## Overview

The Fundus Image Manager includes a sophisticated medical image viewer specifically designed for retinal fundus image analysis in the grading workflow. This viewer provides professional-grade tools for detailed examination and diagnosis of retinal images.

## Quick Start

### Basic Navigation
- **Zoom**: Mouse wheel or pinch gestures (touch devices)
- **Pan**: Click and drag to move the image
- **Reset View**: Double-click to return to original position
- **Keyboard Shortcuts**: Use keyboard for precise control (see shortcuts section)

### Accessing the Viewer
The image viewer is automatically available when you open any grading task. The image appears in the main viewing area with controls overlaid for easy access.

## Core Features

### 1. Zoom and Pan Controls

#### Zoom Levels
- **Range**: 40% - 500% magnification
- **Default**: 100% (actual size)
- **Precision**: 1% increments for fine control

#### Pan Functionality
- **Range**: ±600 pixels horizontally and vertically
- **Smooth Movement**: Real-time pan with visual feedback
- **Reset**: Double-click or use reset button to center image

#### Usage Methods
```
Mouse:
  - Scroll wheel: Zoom in/out
  - Click + Drag: Pan image
  - Double-click: Reset view

Keyboard:
  - +/- keys: Zoom in/out
  - Arrow keys: Pan (10px increments)
  - Home: Reset view
```

### 2. Loupe Magnifier

#### Purpose
The loupe provides localized magnification for detailed examination of specific regions without changing the overall zoom level.

#### Configuration
- **Size**: 100-500 pixels diameter (default: 200px)
- **Magnification**: 1.0x - 4.0x zoom level (default: 2.0x)
- **Activation**: Toggle on/off or auto-show on hover

#### Usage
1. Enable loupe using the toolbar button or keyboard shortcut
2. Move cursor over image to see magnified area
3. Adjust size and magnification in settings
4. Position stays centered on cursor location

#### Medical Applications
- Detailed optic nerve examination
- Microaneurysm detection
- Vascular abnormalities assessment
- Fine lesion characterization

### 3. Image Enhancement Controls

#### Brightness Adjustment
- **Range**: 0.5 - 1.5 (50% - 150% brightness)
- **Default**: 1.0 (normal brightness)
- **Use Case**: Compensate for over/under-exposed images
- **Keyboard**: B/Shift+B for fine adjustment

#### Contrast Adjustment
- **Range**: 0.5 - 1.5 (50% - 150% contrast)
- **Default**: 1.0 (normal contrast)
- **Use Case**: Enhance lesion visibility, improve image clarity
- **Keyboard**: C/Shift+C for fine adjustment

#### Clinical Applications
- **Low Brightness**: Better visualization of dark lesions
- **High Brightness**: Examination of retinal periphery
- **Low Contrast**: Subtle lesion detection
- **High Contrast**: Boundary definition enhancement

### 4. Specialized Filters

#### Red-Free Filter
- **Purpose**: Removes red wavelengths to enhance vessel visibility
- **Clinical Use**:
  - Improved visualization of retinal vessels
  - Better detection of nerve fiber layer defects
  - Enhanced microaneurysm visibility
  - Hemorrhage boundary definition

#### Green Boost Filter
- **Purpose**: Amplifies green wavelengths for enhanced contrast
- **Clinical Use**:
  - Improved drusen visibility
  - Enhanced retinal pigment epithelium (RPE) changes
  - Better geographic atrophy assessment

#### Blue Mono Filter
- **Purpose**: Blue channel monochrome conversion
- **Clinical Use**:
  - Exudate visualization
  - Cotton wool spot identification
  - Optic disc edema assessment

#### Contrast Filter
- **Purpose**: High-contrast monochrome conversion
- **Clinical Use**:
  - General lesion detection
  - Boundary definition
  - Educational and presentation purposes

#### Gray Scale Filter
- **Purpose**: Standard grayscale conversion
- **Clinical Use**:
  - Color-blind friendly viewing
  - Standardized assessment
  - Publication preparation

### 5. Settings and Presets

#### Personal Settings
Your viewer preferences are automatically saved and persist across:
- Different sessions
- Multiple devices
- Browser restarts
- System upgrades

#### Settings Include
- Zoom level and pan position
- Loupe size and magnification
- Brightness and contrast levels
- Active filter selection
- Loupe enable/disable state

#### Presets System
Create up to 5 named presets for quick access to common viewing configurations:

**Example Presets:**

1. **"General Screening"**
   - Zoom: 100%
   - Filter: None
   - Loupe: Enabled (200px, 2.0x)
   - Brightness/Contrast: Normal

2. **"Drusen Assessment"**
   - Zoom: 150%
   - Filter: Green Boost
   - Loupe: Enabled (250px, 2.5x)
   - Brightness: 1.2, Contrast: 1.1

3. **"Vascular Examination"**
   - Zoom: 120%
   - Filter: Red-Free
   - Loupe: Enabled (200px, 3.0x)
   - Brightness: 1.1, Contrast: 1.2

4. **"Hemorrhage Detection"**
   - Zoom: 130%
   - Filter: Red-Free
   - Loupe: Enabled (300px, 2.0x)
   - Brightness: 0.9, Contrast: 1.3

5. **"Optic Nerve Analysis"**
   - Zoom: 200%
   - Filter: Blue Mono
   - Loupe: Enabled (200px, 4.0x)
   - Brightness: 1.0, Contrast: 1.0

#### Managing Presets
- **Save**: Current settings → Save to slot (1-5)
- **Load**: Click preset slot to apply settings
- **Name**: Assign descriptive names for easy identification
- **Delete**: Remove unwanted presets
- **Overwrite**: Update existing presets with new settings

## Interface Elements

### Main Toolbar
Located at the top of the viewer, providing quick access to essential functions:

```
[Zoom Out] [Zoom Level] [Zoom In] [Reset] | [Loupe] | [Filters] | [Presets] | [Settings]
```

### Zoom Controls
- **Zoom Out**: Decrease magnification
- **Zoom Level Display**: Current zoom percentage
- **Zoom In**: Increase magnification
- **Reset View**: Return to default zoom and center

### Loupe Controls
- **Toggle**: Enable/disable loupe
- **Size Slider**: Adjust loupe diameter
- **Magnification Slider**: Adjust zoom level
- **Position**: Follows cursor when enabled

### Filter Selection
Dropdown menu with available filters:
- None (default)
- Red-Free
- Green Boost
- Blue Mono
- Contrast
- Gray Scale

### Preset Management
Slots 1-5 for quick preset access:
- **Empty Slot**: Click to save current settings
- **Saved Preset**: Click to load, right-click to manage
- **Visual Indicators**: Color-coded by filter type

### Settings Panel
Advanced configuration options:
- Fine-tune brightness/contrast
- Adjust loupe parameters
- Reset to defaults
- Export/import settings

## Keyboard Shortcuts

### Navigation Controls
```
Zoom:
  +/=     : Zoom in
  -/_     : Zoom out
  0       : Reset to 100%
  Home    : Reset view (center and 100%)

Pan:
  Arrow Keys : Pan (10px increments)
  Shift + Arrows : Pan faster (50px)
  PageUp/PageDown : Pan vertical
  Home/End       : Pan horizontal
```

### Tool Controls
```
Loupe:
  L       : Toggle loupe on/off
  ]/[     : Increase/decrease loupe size
  }/{     : Increase/decrease loupe magnification

Filters:
  1       : No filter
  2       : Red-Free
  3       : Green Boost
  4       : Blue Mono
  5       : Contrast
  6       : Gray Scale

Adjustments:
  B/Shift+B : Decrease/Increase brightness
  C/Shift+C : Decrease/Increase contrast
  R       : Reset all adjustments
```

### Preset Controls
```
F1-F5    : Load preset 1-5
Ctrl+F1-F5 : Save current settings to preset 1-5
Ctrl+Shift+F1-F5 : Delete preset 1-5
```

### Grading Workflow
```
Tab     : Next form field
Enter   : Submit grade (when form is complete)
Escape  : Cancel/Close
```

## Integration with Grading Workflow

### Context Awareness
The viewer automatically adjusts based on the current grading context:

#### Disease-Specific Presets
- **Diabetic Retinopathy**: Optimized for microaneurysm and hemorrhage detection
- **Glaucoma**: Enhanced optic nerve head visualization
- **AMD**: Improved drusen and geographic atrophy assessment

#### Task-Specific Behavior
- **Resident Grading**: Standard viewing with educational features
- **Resident2 Grading**: Independent assessment without resident grades visible
- **Arbitration**: Comparison tools and access to previous grades

### Performance Optimization
- **Image Preloading**: Loads next task image in background
- **Progressive Loading**: Shows low-quality preview first, then high-quality
- **Caching**: Stores frequently accessed images locally
- **Memory Management**: Automatic cleanup of unused image data

### Quality Assurance
- **Viewing History**: Tracks zoom levels, filters used for audit trails
- **Standardization**: Consistent viewing parameters across graders
- **Compliance**: Meets medical imaging standards and requirements

## Clinical Best Practices

### Systematic Examination
1. **Initial Assessment**: Start with 100% zoom, no filters
2. **Posterior Pole**: Examine optic disc, macula, major vessels
3. **Periphery**: Use zoom and pan for peripheral examination
4. **Lesion Detection**: Apply appropriate filters for specific findings
5. **Documentation**: Save presets for reproducible examination conditions

### Filter Selection Guidelines
```
Clinical Scenario → Recommended Filter

General screening → No filter or Red-Free
Microaneurysms → Red-Free
Hemorrhages → Red-Free or Contrast
Drusen → Green Boost
Exudates → Blue Mono or Green Boost
Nerve fiber layer → Red-Free
Optic disc → Blue Mono or Contrast
```

### Magnification Best Practices
- **Macular examination**: 150-200% zoom
- **Optic nerve assessment**: 200-300% zoom
- **Peripheral evaluation**: 100-120% zoom
- **Fine detail examination**: Use loupe with 3.0-4.0x magnification

### Calibration and Quality
- **Display Calibration**: Regular monitor calibration recommended
- **Color Accuracy**: Use medical-grade displays when available
- **Ambient Lighting**: Controlled lighting environment for consistent viewing
- **Break Periods**: Regular breaks to prevent eye strain during extended grading

## Technical Specifications

### Supported Image Formats
- JPEG, PNG (standard formats)
- DICOM (medical imaging format - future enhancement)
- High-resolution images up to 4K
- Lossless compression options

### Performance Requirements
- **Minimum**: Modern browser with HTML5 Canvas support
- **Recommended**: Chrome 90+, Firefox 88+, Safari 14+
- **Memory**: 4GB RAM minimum, 8GB recommended for large images
- **Network**: Broadband connection for optimal image loading

### Browser Compatibility
- **Desktop**: Full feature support
- **Tablet**: Touch gestures supported, preset management available
- **Mobile**: Limited functionality, emergency use only
- **Progressive Enhancement**: Core functionality works on all supported browsers

## Troubleshooting

### Common Issues

#### Image Loading Problems
- **Symptom**: Image doesn't load or shows error
- **Solutions**:
  - Check internet connection
  - Refresh the page
  - Try a different browser
  - Contact support if persistent

#### Performance Issues
- **Symptom**: Slow response or lag
- **Solutions**:
  - Close other browser tabs
  - Reduce zoom level for very large images
  - Disable automatic image preloading in settings
  - Use a more powerful device

#### Settings Not Saving
- **Symptom**: Preferences reset on reload
- **Solutions**:
  - Check network connection
  - Verify login status
  - Clear browser cache and cookies
  - Contact administrator

#### Loupe Not Working
- **Symptom**: Loupe doesn't appear or follow cursor
- **Solutions**:
  - Ensure loupe is enabled in toolbar
  - Check if cursor is over image area
  - Try disabling and re-enabling loupe
  - Update browser to latest version

### Error Messages
- **"Image not available"**: Check if task is still assigned to you
- **"Settings failed to save"**: Network connection issue, try again
- **"Invalid preset data"**: Reset settings to defaults and try again

### Support Resources
- **In-App Help**: Click help icon in viewer toolbar
- **User Manual**: Comprehensive documentation available online
- **Video Tutorials**: Step-by-step guides for common tasks
- **Technical Support**: Contact system administrator for persistent issues

## Advanced Features

### Comparison Tools (Arbitration)
When grading in arbitration mode:
- **Side-by-side view**: Compare resident and resident2 grades
- **Overlay mode**: Superimpose previous grades for comparison
- **Difference highlighting**: Automatically highlight areas of disagreement
- **Synchronized navigation**: Linked pan/zoom across multiple images

### Measurement Tools (Planned)
Future enhancements may include:
- **Distance measurement**: Calibrated measurement tools
- **Area calculation**: Lesion area quantification
- **Angle measurement**: Vascular angle assessment
- **Calibration**: Automatic calibration based on image metadata

### Export and Reporting
- **Current view export**: Save current viewer state as image
- **Settings export**: Backup personal settings and presets
- **Session recording**: Record viewing session for training purposes
- **Audit trail**: Comprehensive logging of all viewer interactions

## Accessibility Features

### Vision Support
- **High contrast mode**: Enhanced interface visibility
- **Screen reader support**: Compatible with major screen readers
- **Keyboard navigation**: Full keyboard control of all features
- **Text-to-speech**: Spoken feedback for interface elements

### Motor Assistance
- **Large click targets**: Easier selection for users with motor difficulties
- **Gesture simplification**: Reduced complexity for touch interfaces
- **Voice control**: Future enhancement for hands-free operation

### Cognitive Support
- **Clear visual indicators**: Obvious state changes and feedback
- **Consistent interface**: Predictable behavior across all functions
- **Progressive disclosure**: Advanced features hidden until needed

---

## Quick Reference Card

### Essential Keyboard Shortcuts
```
+ / -        : Zoom in/out
L           : Toggle loupe
1-6          : Select filters
F1-F5        : Load presets
R           : Reset adjustments
Home         : Reset view
```

### Clinical Filter Guide
```
Red-Free     : Vessels, hemorrhages, microaneurysms
Green Boost  : Drusen, RPE changes
Blue Mono    : Exudates, cotton wool spots
Contrast     : General lesion enhancement
Gray Scale   : Color-blind friendly
```

### Emergency Procedures
1. **Image not visible**: Refresh page, check assignment
2. **Viewer frozen**: Restart browser, clear cache
3. **Settings lost**: Reconfigure preferences
4. **Performance poor**: Reduce zoom, close other tabs

---

**Last Updated**: November 10, 2025
**Version**: 1.0
**Compatibility**: All modern browsers (Chrome 90+, Firefox 88+, Safari 14+)
**Requirements**: Internet connection, 4GB RAM minimum