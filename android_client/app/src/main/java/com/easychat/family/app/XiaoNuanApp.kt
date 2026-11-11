package com.easychat.family.app

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.easychat.family.R
import com.easychat.family.core.designsystem.XnSpacing
import com.easychat.family.feature.chat.ChatDetailScreen
import com.easychat.family.feature.chat.ChatListScreen
import com.easychat.family.feature.chat.ChatViewModel
import com.easychat.family.feature.life.LifeScreen
import com.easychat.family.feature.onboarding.LoginScreen
import com.easychat.family.feature.onboarding.OnboardingViewModel
import com.easychat.family.feature.onboarding.ServerConfigScreen
import com.easychat.family.feature.onboarding.WelcomeScreen
import com.easychat.family.feature.profile.ProfileScreen
import com.easychat.family.feature.today.TodayScreen
import kotlinx.coroutines.launch

/** 路由名(canonical session_id 在 WP2 经真实历史读取)。 */
object Routes {
    const val WELCOME = "onboarding/welcome"
    const val SERVER = "onboarding/server"
    const val LOGIN = "onboarding/login"
    const val TODAY = "today"
    const val CHAT = "chat"
    const val LIFE = "life"
    const val PROFILE = "profile"
    const val CHAT_DETAIL = "chat/detail/{sessionId}?wechat={wechat}"

    fun chatDetail(sessionId: String, wechat: Boolean) = "chat/detail/$sessionId?wechat=$wechat"

    val topLevel = listOf(TODAY, CHAT, LIFE, PROFILE)
}

private data class TabSpec(val route: String, val label: String, val iconRes: Int)

private val tabs = listOf(
    TabSpec(Routes.TODAY, "今天", R.drawable.ic_nav_today),
    TabSpec(Routes.CHAT, "聊天", R.drawable.ic_nav_chat),
    TabSpec(Routes.LIFE, "生活", R.drawable.ic_nav_life),
    TabSpec(Routes.PROFILE, "我的", R.drawable.ic_nav_me),
)

/** 应用骨架:起始页按真实登录态决定;401 过期自动退回登录(设计 §5.1/§7.2)。 */
@Composable
fun XiaoNuanApp(navController: NavHostController = rememberNavController()) {
    val app = androidx.compose.ui.platform.LocalContext.current.applicationContext as XiaoNuanApplication
    val container = app.container

    var startRoute by remember { androidx.compose.runtime.mutableStateOf<String?>(null) }
    LaunchedEffect(Unit) {
        val hasToken = container.tokens.token() != null
        val hasUser = container.conn.username().isNotBlank()
        startRoute = if (hasToken && hasUser) Routes.TODAY else Routes.WELCOME
    }
    val snackbar = remember { SnackbarHostState() }

    // 会话过期:提示并退回登录
    val expired by container.sessionExpired.collectAsState()
    LaunchedEffect(expired) {
        if (expired) {
            snackbar.showSnackbar("登录已过期,请重新登录")
            container.clearSessionExpiredFlag()
            navController.navigate(Routes.LOGIN) {
                popUpTo(0) { inclusive = true }
            }
        }
    }

    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val showBottomBar = currentRoute in Routes.topLevel

    val onboardingVm: OnboardingViewModel = viewModel()
    val chatVm: ChatViewModel = viewModel()

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            if (showBottomBar) {
                NavigationBar(
                    containerColor = MaterialTheme.colorScheme.surface,
                    tonalElevation = XnSpacing.sm,
                ) {
                    tabs.forEach { tab ->
                        val selected = currentRoute == tab.route
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                navController.navigate(tab.route) {
                                    popUpTo(navController.graph.findStartDestination().id) { saveState = true }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = {
                                Icon(
                                    painterResource(tab.iconRes),
                                    contentDescription = tab.label,
                                    tint = if (selected) MaterialTheme.colorScheme.primary
                                    else MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            },
                            label = { Text(tab.label) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedTextColor = MaterialTheme.colorScheme.primary,
                                unselectedTextColor = MaterialTheme.colorScheme.onSurfaceVariant,
                            ),
                        )
                    }
                }
            }
        },
    ) { padding ->
        when (val start = startRoute) {
            null -> Unit // 启动期读凭证(毫秒级)
            else -> NavHost(
                navController = navController,
                startDestination = start,
                modifier = Modifier.padding(padding),
            ) {
                composable(Routes.WELCOME) {
                    WelcomeScreen(
                        onStart = { navController.navigate(Routes.SERVER) },
                        onConfigureServer = { navController.navigate(Routes.SERVER) },
                    )
                }
                composable(Routes.SERVER) {
                    ServerConfigScreen(
                        vm = onboardingVm,
                        onConnected = { navController.navigate(Routes.LOGIN) },
                        onBack = { navController.popBackStack() },
                    )
                }
                composable(Routes.LOGIN) {
                    LoginScreen(
                        vm = onboardingVm,
                        onLoggedIn = {
                            navController.navigate(Routes.TODAY) {
                                popUpTo(0) { inclusive = true }
                            }
                        },
                        onBack = { navController.popBackStack() },
                    )
                }
                composable(Routes.TODAY) {
                    TodayScreen(
                        onOpenChat = { navController.navigate(Routes.CHAT) },
                        onOpenLife = { navController.navigate(Routes.LIFE) },
                        onOpenWechatChat = { navController.navigate(Routes.CHAT) },
                    )
                }
                composable(Routes.CHAT) {
                    ChatListScreen(
                        vm = chatVm,
                        onOpenChat = { sessionId ->
                            navController.navigate(Routes.chatDetail(sessionId, wechat = false))
                        },
                        onNewChat = { navController.navigate(Routes.chatDetail("new", wechat = false)) },
                    )
                }
                composable(Routes.LIFE) {
                    LifeScreen()
                }
                composable(Routes.PROFILE) {
                    val scope = androidx.compose.runtime.rememberCoroutineScope()
                    ProfileScreen(
                        onLogout = {
                            scope.launch {
                                container.auth.logout()
                                container.clearSessionExpiredFlag()
                                navController.navigate(Routes.WELCOME) {
                                    popUpTo(0) { inclusive = true }
                                }
                            }
                        },
                    )
                }
                composable(Routes.CHAT_DETAIL) { entry ->
                    val sessionId = entry.arguments?.getString("sessionId") ?: ""
                    val wechat = entry.arguments?.getString("wechat") == "true"
                    LaunchedEffect(sessionId) {
                        when {
                            sessionId == "new" -> chatVm.openNew()
                            sessionId.isNotBlank() -> chatVm.openExisting(sessionId)
                        }
                    }
                    ChatDetailScreen(
                        vm = chatVm,
                        wechat = wechat,
                        onBack = { navController.popBackStack() },
                        onContinueChat = {
                            // 独立 App 会话 + 可编辑背景草稿(发送才提交,设计 §5.3)
                            navController.navigate(Routes.chatDetail("new", wechat = false)) {
                                popUpTo(Routes.CHAT)
                            }
                        },
                    )
                }
            }
        }
    }
}

