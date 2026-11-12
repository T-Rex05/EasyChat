# 保留 kotlinx.serialization 生成的 serializer(发布混淆时必需)
-if @kotlinx.serialization.Serializable class **
-keepclassmembers class <1> {
    static <1>$Companion Companion;
}
-keepclasseswithmembers class <1>$Companion {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.easychat.family.**$$serializer { *; }
