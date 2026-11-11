package com.easychat.family.app

import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
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
import com.easychat.family.feature.life.LifeScreen
import com.easychat.family.feature.onboarding.LoginScreen
import com.easychat.family.feature.onboarding.ServerConfigScreen
import com.easychat.family.feature.onboarding.WelcomeScreen
import com.easychat.family.feature.profile.ProfileScreen
import com.easychat.family.feature.today.TodayScreen

/** 路由名(首版单模块;正式会话 id 在 WP2 接入)。 */
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

private data class TabSpec(val route: String, val label: String, val iconRes: Int, val selectedIconRes: Int)

private val tabs = listOf(
    TabSpec(Routes.TODAY, "今天", R.drawable.ic_nav_today, R.drawable.ic_nav_today),
    TabSpec(Routes.CHAT, "聊天", R.drawable.ic_nav_chat, R.drawable.ic_nav_chat),
    TabSpec(Routes.LIFE, "生活", R.drawable.ic_nav_life, R.drawable.ic_nav_life),
    TabSpec(Routes.PROFILE, "我的", R.drawable.ic_nav_me, R.drawable.ic_nav_me),
)

/** 应用骨架:WP1 首启进入欢迎页(真实流程按登录态决定,WP2 接入)。 */
@Composable
fun XiaoNuanApp(navController: NavHostController = rememberNavController()) {
    val backStack by navController.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val showBottomBar = currentRoute in Routes.topLevel

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
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
                                    painterResource(if (selected) tab.selectedIconRes else tab.iconRes),
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
        NavHost(
            navController = navController,
            startDestination = Routes.WELCOME,
            modifier = Modifier.padding(padding),
        ) {
            composable(Routes.WELCOME) {
                WelcomeScreen(
                    onStart = { navController.navigate(Routes.SERVER) },
                    onConfigureServer = { navController.navigate(Routes.SERVER) },
                )
            }
            composable(Routes.SERVER) {
                ServerConfigScreen(onConnected = { navController.navigate(Routes.LOGIN) }, onBack = { navController.popBackStack() })
            }
            composable(Routes.LOGIN) {
                LoginScreen(onLoggedIn = {
                    navController.navigate(Routes.TODAY) {
                        popUpTo(Routes.WELCOME) { inclusive = true }
                    }
                }, onBack = { navController.popBackStack() })
            }
            composable(Routes.TODAY) {
                TodayScreen(
                    onOpenChat = { navController.navigate(Routes.CHAT) },
                    onOpenLife = { navController.navigate(Routes.LIFE) },
                    onOpenWechatChat = { navController.navigate(Routes.chatDetail("wx_demo_01", wechat = true)) },
                )
            }
            composable(Routes.CHAT) {
                ChatListScreen(
                    onOpenChat = { sessionId -> navController.navigate(Routes.chatDetail(sessionId, wechat = false)) },
                    onOpenWechatChat = { sessionId -> navController.navigate(Routes.chatDetail(sessionId, wechat = true)) },
                )
            }
            composable(Routes.LIFE) {
                LifeScreen()
            }
            composable(Routes.PROFILE) {
                ProfileScreen()
            }
            composable(Routes.CHAT_DETAIL) { entry ->
                val sessionId = entry.arguments?.getString("sessionId") ?: ""
                val wechat = entry.arguments?.getString("wechat") == "true"
                ChatDetailScreen(
                    sessionId = sessionId,
                    wechat = wechat,
                    onBack = { navController.popBackStack() },
                    // 带着这段聊一聊:新建独立 App 会话(WP2 接入真实创建)
                    onContinueChat = {
                        navController.navigate(Routes.chatDetail("app_new_from_wx", wechat = false)) {
                            popUpTo(Routes.CHAT)
                        }
                    },
                )
            }
        }
    }
}
