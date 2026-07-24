const local: App.I18n.Schema = {
  system: {
    title: 'Douyin Live Operations',
    updateTitle: 'System Version Update Notification',
    updateContent: 'A new version of the system has been detected. Do you want to refresh the page immediately?',
    updateConfirm: 'Refresh immediately',
    updateCancel: 'Later'
  },
  common: {
    action: 'Action',
    add: 'Add',
    addSuccess: 'Add Success',
    backToHome: 'Back to home',
    batchDelete: 'Batch Delete',
    cancel: 'Cancel',
    close: 'Close',
    check: 'Check',
    selectAll: 'Select All',
    expandColumn: 'Expand Column',
    columnSetting: 'Column Setting',
    config: 'Config',
    confirm: 'Confirm',
    delete: 'Delete',
    deleteSuccess: 'Delete Success',
    confirmDelete: 'Are you sure you want to delete?',
    detail: 'Detail',
    edit: 'Edit',
    warning: 'Warning',
    error: 'Error',
    index: 'Index',
    keywordSearch: 'Please enter keyword',
    logout: 'Logout',
    logoutConfirm: 'Are you sure you want to log out?',
    lookForward: 'Coming soon',
    modify: 'Modify',
    modifySuccess: 'Modify Success',
    noData: 'No Data',
    operate: 'Operate',
    pleaseCheckValue: 'Please check whether the value is valid',
    refresh: 'Refresh',
    reset: 'Reset',
    search: 'Search',
    switch: 'Switch',
    tip: 'Tip',
    trigger: 'Trigger',
    update: 'Update',
    updateSuccess: 'Update Success',
    userCenter: 'User Center',
    yesOrNo: {
      yes: 'Yes',
      no: 'No'
    }
  },
  request: {
    logout: 'Logout user after request failed',
    logoutMsg: 'User status is invalid, please log in again',
    logoutWithModal: 'Pop up modal after request failed and then log out user',
    logoutWithModalMsg: 'User status is invalid, please log in again',
    refreshToken: 'The requested token has expired, refresh the token',
    tokenExpired: 'The requested token has expired'
  },
  theme: {
    themeDrawerTitle: 'Theme Configuration',
    tabs: {
      appearance: 'Appearance',
      layout: 'Layout',
      general: 'General',
      preset: 'Preset'
    },
    appearance: {
      themeSchema: {
        title: 'Theme Schema',
        light: 'Light',
        dark: 'Dark',
        auto: 'Follow System'
      },
      grayscale: 'Grayscale',
      colourWeakness: 'Colour Weakness',
      themeColor: {
        title: 'Theme Color',
        primary: 'Primary',
        info: 'Info',
        success: 'Success',
        warning: 'Warning',
        error: 'Error',
        followPrimary: 'Follow Primary'
      },
      themeRadius: {
        title: 'Theme Radius'
      },
      recommendColor: 'Apply Recommended Color Algorithm',
      recommendColorDesc: 'The recommended color algorithm refers to',
      preset: {
        title: 'Theme Presets',
        apply: 'Apply',
        applySuccess: 'Preset applied successfully',
        default: {
          name: 'Default Preset',
          desc: 'Default theme preset with balanced settings'
        },
        dark: {
          name: 'Dark Preset',
          desc: 'Dark theme preset for night time usage'
        },
        compact: {
          name: 'Compact Preset',
          desc: 'Compact layout preset for small screens'
        },
        azir: {
          name: "Azir's Preset",
          desc: 'It is a cold and elegant preset that Azir likes'
        }
      }
    },
    layout: {
      layoutMode: {
        title: 'Layout Mode',
        vertical: 'Vertical Mode',
        horizontal: 'Horizontal Mode',
        'vertical-mix': 'Vertical Mix Mode',
        'vertical-hybrid-header-first': 'Left Hybrid Header-First',
        'top-hybrid-sidebar-first': 'Top-Hybrid Sidebar-First',
        'top-hybrid-header-first': 'Top-Hybrid Header-First',
        vertical_detail: 'Vertical menu layout, with the menu on the left and content on the right.',
        'vertical-mix_detail':
          'Vertical mix-menu layout, with the primary menu on the dark left side and the secondary menu on the lighter left side.',
        'vertical-hybrid-header-first_detail':
          'Left hybrid layout, with the primary menu at the top, the secondary menu on the dark left side, and the tertiary menu on the lighter left side.',
        horizontal_detail: 'Horizontal menu layout, with the menu at the top and content below.',
        'top-hybrid-sidebar-first_detail':
          'Top hybrid layout, with the primary menu on the left and the secondary menu at the top.',
        'top-hybrid-header-first_detail':
          'Top hybrid layout, with the primary menu at the top and the secondary menu on the left.'
      },
      tab: {
        title: 'Tab Settings',
        visible: 'Tab Visible',
        cache: 'Tag Bar Info Cache',
        cacheTip: 'Keep the tab bar information after leaving the page',
        height: 'Tab Height',
        mode: {
          title: 'Tab Mode',
          slider: 'Slider',
          chrome: 'Chrome',
          button: 'Button'
        },
        closeByMiddleClick: 'Close Tab by Middle Click',
        closeByMiddleClickTip: 'Enable closing tabs by clicking with the middle mouse button'
      },
      header: {
        title: 'Header Settings',
        height: 'Header Height',
        breadcrumb: {
          visible: 'Breadcrumb Visible',
          showIcon: 'Breadcrumb Icon Visible'
        }
      },
      sider: {
        title: 'Sider Settings',
        inverted: 'Dark Sider',
        width: 'Sider Width',
        collapsedWidth: 'Sider Collapsed Width',
        mixWidth: 'Mix Sider Width',
        mixCollapsedWidth: 'Mix Sider Collapse Width',
        mixChildMenuWidth: 'Mix Child Menu Width',
        autoSelectFirstMenu: 'Auto Select First Submenu',
        autoSelectFirstMenuTip:
          'When a first-level menu is clicked, the first submenu is automatically selected and navigated to the deepest level'
      },
      footer: {
        title: 'Footer Settings',
        visible: 'Footer Visible',
        fixed: 'Fixed Footer',
        height: 'Footer Height',
        right: 'Right Footer'
      },
      content: {
        title: 'Content Area Settings',
        scrollMode: {
          title: 'Scroll Mode',
          tip: 'The theme scroll only scrolls the main part, the outer scroll can carry the header and footer together',
          wrapper: 'Wrapper',
          content: 'Content'
        },
        page: {
          animate: 'Page Animate',
          mode: {
            title: 'Page Animate Mode',
            fade: 'Fade',
            'fade-slide': 'Slide',
            'fade-bottom': 'Fade Zoom',
            'fade-scale': 'Fade Scale',
            'zoom-fade': 'Zoom Fade',
            'zoom-out': 'Zoom Out',
            none: 'None'
          }
        },
        fixedHeaderAndTab: 'Fixed Header And Tab'
      }
    },
    general: {
      title: 'General Settings',
      watermark: {
        title: 'Watermark Settings',
        visible: 'Watermark Full Screen Visible',
        text: 'Custom Watermark Text',
        enableUserName: 'Enable User Name Watermark',
        enableTime: 'Show Current Time',
        timeFormat: 'Time Format'
      },
      multilingual: {
        title: 'Multilingual Settings',
        visible: 'Display multilingual button'
      },
      globalSearch: {
        title: 'Global Search Settings',
        visible: 'Display GlobalSearch button'
      }
    },
    configOperation: {
      copyConfig: 'Copy Config',
      copySuccessMsg: 'Copy Success, Please replace the variable "themeSettings" in "src/theme/settings.ts"',
      resetConfig: 'Reset Config',
      resetSuccessMsg: 'Reset Success'
    }
  },
  route: {
    login: 'Login',
    403: 'No Permission',
    404: 'Page Not Found',
    500: 'Server Error',
    'iframe-page': 'Iframe',
    home: 'Home',
    dashboard: 'Dashboard',
    collector: 'Collector',
    'live-sessions': 'Live Sessions',
    'live-session-detail': 'Live Session Detail',
    transcripts: 'Transcripts',
    analysis: 'AI Analysis',
    knowledge: 'Knowledge Base',
    'anchor-schedule': 'Anchor Schedule',
    'prompt-management': 'Prompt Management',
    'user-management': 'User Management'
  },
  page: {
    login: {
      common: {
        loginOrRegister: 'Login / Register',
        userNamePlaceholder: 'Please enter user name',
        phonePlaceholder: 'Please enter phone number',
        codePlaceholder: 'Please enter verification code',
        passwordPlaceholder: 'Please enter password',
        confirmPasswordPlaceholder: 'Please enter password again',
        codeLogin: 'Verification code login',
        confirm: 'Confirm',
        back: 'Back',
        validateSuccess: 'Verification passed',
        loginSuccess: 'Login successfully',
        welcomeBack: 'Welcome back, {userName} !'
      },
      pwdLogin: {
        title: 'Password Login',
        rememberMe: 'Remember me',
        forgetPassword: 'Forget password?',
        register: 'Register',
        otherAccountLogin: 'Other Account Login',
        otherLoginMode: 'Other Login Mode',
        superAdmin: 'Super Admin',
        admin: 'Admin',
        user: 'User'
      },
      codeLogin: {
        title: 'Verification Code Login',
        getCode: 'Get verification code',
        reGetCode: 'Reacquire after {time}s',
        sendCodeSuccess: 'Verification code sent successfully',
        imageCodePlaceholder: 'Please enter image verification code'
      },
      register: {
        title: 'Register',
        agreement: 'I have read and agree to',
        protocol: '《User Agreement》',
        policy: '《Privacy Policy》'
      },
      resetPwd: {
        title: 'Reset Password'
      },
      bindWeChat: {
        title: 'Bind WeChat'
      }
    },
    dashboard: {
      placeholder: 'DataEase dashboard is not configured',
      placeholderDesc: 'Configure the URL to display live metrics, conversion funnels and audience profiles.',
      todayLeads: 'Today Leads',
      onlineUsers: 'Online Users',
      validLeadRate: 'Valid Lead Rate',
      leadCost: 'Lead Cost',
      unitPeople: '',
      unitYuan: '¥'
    },
    collector: {
      statusTitle: 'Collector Status',
      connected: 'Connected',
      disconnected: 'Disconnected',
      connectTime: 'Connect Time',
      accountList: 'Account List',
      accountName: 'Account Name',
      douyinId: 'Douyin ID',
      loginStatus: 'Login Status',
      lastLogin: 'Last Login',
      logTitle: 'Collection Logs',
      logTime: 'Time',
      logLevel: 'Level',
      logMessage: 'Message',
      statusValid: 'Valid',
      statusExpired: 'Expired',
      levelInfo: 'Info',
      levelWarn: 'Warning',
      levelError: 'Error',
      scanLogin: 'QR Login',
      scanQrCode: 'Scan QR code with Douyin',
      loginSuccess: 'Login successful',
      loginFailed: 'Login failed',
      loginTimeout: 'QR code expired, please re-scan',
      reLogin: 'Re-login',
      deleteAccount: 'Delete Account',
      confirmDelete: 'Are you sure you want to delete this account?',
      noAccount: 'No accounts yet',
      taskList: 'Task List',
      taskType: 'Task Type',
      taskStatus: 'Task Status',
      loading: 'Loading...',
      activeTasks: 'Active Tasks',
      neverLogin: 'Never Logged In',
      loggedIn: 'Logged In'
    },
    'live-sessions': {
      title: 'Live Sessions',
      date: 'Date',
      anchorName: 'Anchor',
      sessionTitle: 'Session Title',
      sessionStatus: 'Status',
      startTime: 'Start',
      endTime: 'End',
      duration: 'Duration',
      onlineUsers: 'Peak Online',
      totalLeads: 'Total Leads',
      validLeads: 'Valid Leads',
      leads: 'Leads',
      viewCount: 'View Count',
      newFollowers: 'New Followers',
      commentsCount: 'Comments',
      adCost: 'Ad Cost',
      exposureEnterRate: 'Exposure Enter Rate',
      commentRate: 'Comment Rate',
      interactionRate: 'Interaction Rate',
      detailTitle: 'Session Detail',
      basicInfo: 'Basic Info',
      timeInfo: 'Time Info',
      coreMetrics: 'Core Metrics',
      dashboardLink: 'View Dashboard',
      refresh: 'Refresh',
      loading: 'Loading...',
      noData: 'No sessions yet. Please collect data first.',
      statusLive: 'Live',
      statusScheduled: 'Scheduled',
      statusEnded: 'Ended',
      trafficSource: 'Traffic Source',
      sourceFollow: 'Follow',
      sourceRecommend: 'Recommend',
      sourceSearch: 'Search',
      sourceOther: 'Other',
      conversion: 'Conversion Funnel',
      stepView: 'View',
      stepInteraction: 'Interaction',
      stepLead: 'Lead',
      stepValid: 'Valid Lead',
      minutes: 'min',
      hours: 'h',
      detail: 'Detail'
    },
    transcripts: {
      title: 'Transcript Segments',
      segmentTime: 'Time',
      content: 'Content',
      duration: 'Duration',
      score: 'AI Score',
      copyFullText: 'Copy Full Text',
      copySuccess: 'Copied successfully',
      timeline: 'Timeline',
      seconds: 's',
      realtimeTranscript: 'Real-time Transcript',
      selectSession: 'Select Session',
      wsConnected: 'Connected',
      wsDisconnected: 'Disconnected',
      transcribing: 'Transcribing...',
      noSession: 'No sessions available',
      statusPending: 'Pending',
      statusProcessing: 'Processing',
      statusCompleted: 'Completed',
      statusFailed: 'Failed'
    },
    analysis: {
      title: 'AI Analysis Report',
      completeness: 'Completeness',
      interactivity: 'Interactivity',
      leadGuidance: 'Lead Guidance',
      overall: 'Overall',
      trendTitle: 'Multi-session Score Trend',
      alertTitle: 'Anomaly Alerts',
      alertDrop: 'Traffic Drop',
      alertDropDesc: 'Online users dropped 45% at 15:30',
      alertInteract: 'Interaction Drop',
      alertInteractDesc: 'Comments decreased 60% after 16:00',
      alertLead: 'Zero Leads',
      alertLeadDesc: 'No new leads from 17:00 to 17:30',
      suggestionTitle: 'Optimization Suggestions',
      suggestion1: 'Add interaction prompts within 15 minutes of going live to improve retention',
      suggestion2: 'Include more lead generation prompts in scripts, remind every 5 minutes',
      suggestion3: 'Use time-limited offers during product showcase segments',
      score: 'pts',
      empty: 'No data'
    },
    knowledge: {
      title: 'Knowledge Base',
      all: 'All',
      transcript: 'Transcripts',
      analysis: 'Analysis',
      suggestion: 'Suggestions',
      itemTitle: 'Title',
      category: 'Category',
      summary: 'Summary',
      source: 'Source',
      time: 'Date',
      chatPlaceholder: 'Ask about synced live session data',
      chatDesc: 'Ask AI questions and receive answers with traceable knowledge sources'
    },
    home: {
      branchDesc:
        'For the convenience of everyone in developing and updating the merge, we have streamlined the code of the main branch, only retaining the homepage menu, and the rest of the content has been moved to the example branch for maintenance. The preview address displays the content of the example branch.',
      greeting: 'Good morning, {userName}, today is another day full of vitality!',
      weatherDesc: 'Today is cloudy to clear, 20℃ - 25℃!',
      projectCount: 'Project Count',
      todo: 'Todo',
      message: 'Message',
      downloadCount: 'Download Count',
      registerCount: 'Register Count',
      schedule: 'Work and rest Schedule',
      study: 'Study',
      work: 'Work',
      rest: 'Rest',
      entertainment: 'Entertainment',
      visitCount: 'Visit Count',
      turnover: 'Turnover',
      dealCount: 'Deal Count',
      projectNews: {
        title: 'Project News',
        moreNews: 'More News',
        desc1: 'Soybean created the open source project soybean-admin on May 28, 2021!',
        desc2: 'Yanbowe submitted a bug to soybean-admin, the multi-tab bar will not adapt.',
        desc3: 'Soybean is ready to do sufficient preparation for the release of soybean-admin!',
        desc4: 'Soybean is busy writing project documentation for soybean-admin!',
        desc5: 'Soybean just wrote some of the workbench pages casually, and it was enough to see!'
      },
      creativity: 'Creativity'
    }
  },
  form: {
    required: 'Cannot be empty',
    userName: {
      required: 'Please enter user name',
      invalid: 'User name format is incorrect'
    },
    phone: {
      required: 'Please enter phone number',
      invalid: 'Phone number format is incorrect'
    },
    pwd: {
      required: 'Please enter password',
      invalid: '6-18 characters, including letters, numbers, and underscores'
    },
    confirmPwd: {
      required: 'Please enter password again',
      invalid: 'The two passwords are inconsistent'
    },
    code: {
      required: 'Please enter verification code',
      invalid: 'Verification code format is incorrect'
    },
    email: {
      required: 'Please enter email',
      invalid: 'Email format is incorrect'
    }
  },
  dropdown: {
    closeCurrent: 'Close Current',
    closeOther: 'Close Other',
    closeLeft: 'Close Left',
    closeRight: 'Close Right',
    closeAll: 'Close All',
    pin: 'Pin Tab',
    unpin: 'Unpin Tab'
  },
  icon: {
    themeConfig: 'Theme Configuration',
    themeSchema: 'Theme Schema',
    lang: 'Switch Language',
    fullscreen: 'Fullscreen',
    fullscreenExit: 'Exit Fullscreen',
    reload: 'Reload Page',
    collapse: 'Collapse Menu',
    expand: 'Expand Menu',
    pin: 'Pin',
    unpin: 'Unpin'
  },
  datatable: {
    itemCount: 'Total {total} items',
    fixed: {
      left: 'Left Fixed',
      right: 'Right Fixed',
      unFixed: 'Unfixed'
    }
  }
};

export default local;
