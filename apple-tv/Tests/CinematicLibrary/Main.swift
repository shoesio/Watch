import Foundation
@main struct Checks {
    static func main() throws {
        func programme(_ episodes:[[String:Any]],film:Bool=false,live:Bool=false,id:String="test",title:String="Test show",favouriteAt:Double=0,poster:String?=nil,genres:[String]=[],archiveYear:Int?=nil,favourite:Bool=true,recent:Bool=true,brandID:String?=nil)->Programme {
            var value:[String:Any] = ["id":id,"title":title,"favourite_at":favouriteAt,"live":live,"film":film,"recent":recent,"favourite":favourite,"genres":genres,"brands":[],"episodes":episodes]
            if let poster {value["poster"]=poster}
            if let archiveYear {value["archive_year"]=archiveYear}
            if let brandID {value["brands"]=[["id":brandID,"name":brandID=="bbc" ? "BBC iPlayer" : brandID,"image":"http://host/static/artwork/brands/"+brandID+".png"]]}
            return try! JSONDecoder.watch.decode(Programme.self,from:JSONSerialization.data(withJSONObject:value))
        }
        func ep(_ id:String,_ season:String,_ number:Int,_ updated:Double=0)->[String:Any] {
            ["id":id,"title":id,"season":season,"episode_number":number,"updated_at":updated,"brands":[]]
        }
        precondition(programme([ep("label","Series 19",1)]).episodes[0].seasonNumber==19)
        precondition(programme([ep("label","Episodes",1)]).episodes[0].seasonNumber==nil)
        let seen=ep("seen","19",1,100)
        precondition(programme([seen,ep("new","19",2)]).hasNewEpisode)
        precondition(programme([seen,ep("new-season","20",1)]).hasNewEpisode)
        precondition(!programme([seen,ep("old","18",8)]).hasNewEpisode)
        precondition(!programme([seen,ep("already-watched","19",2,90)]).hasNewEpisode)
        precondition(!programme([seen,ep("special","Specials",1)]).hasNewEpisode)
        precondition(!programme([ep("unwatched","19",2)]).hasNewEpisode)
        precondition(!programme([seen,ep("new","19",2)],film:true).hasNewEpisode)
        precondition(!programme([seen,ep("new","19",2)],live:true).hasNewEpisode)
        precondition(programme([seen]).poster == nil,"Existing host libraries must decode without portrait artwork")
        let older=programme([],id:"a",title:"Alphabetical first",favouriteAt:50)
        let newer=programme([],id:"z",title:"Recent favourite",favouriteAt:100)
        precondition(BrowseOrdering.personal([older,newer],recommended:[]).first?.id=="z")
        let a=programme([],id:"a",title:"A"),z=programme([],id:"z",title:"Z")
        precondition(BrowseOrdering.personal([a,z],recommended:[z,a]).first?.id=="z")
        precondition(BrowseOrdering.personal([z,a],recommended:[]).first?.id=="z","A tie silently reverted to alphabetic order")
        precondition(programme([],title:"QI XL").editionLabel=="QI XL · Extended")
        precondition(programme([],title:"Taskmaster Bleeped").editionLabel=="Bleeped")
        let pool=(0..<25).map {i in programme([],id:"show-\(i)",title:"Show \(i)",poster:i<9 ? "https://images.example/poster.jpg" : nil,genres:i%2==0 ? ["Comedy"] : ["Drama"],archiveYear:i<5 ? 1999 : nil)}
        let movie=programme([],film:true,id:"film",title:"A film")
        let shelves=EditorialShelves.make(pool+[movie],films:false,year:2026)
        precondition(shelves.allSatisfy{$0.programmes.allSatisfy{!$0.film && !$0.live}})
        precondition(shelves.allSatisfy{$0.programmes.count>=3},"A short tail produced an orphan shelf")
        precondition(shelves.filter{$0.layout != .landscape}.allSatisfy{$0.programmes.allSatisfy{$0.poster != nil}},"Portrait rows used landscape crops")
        precondition(Set(shelves.flatMap{$0.programmes.map(\.id)})==Set(pool.map(\.id)),"A title disappeared while theming")
        precondition(shelves.first(where:{$0.id=="archive"})?.programmes.allSatisfy{($0.archiveYear ?? 9999)<=2011} == true)
        precondition(EditorialShelves.make(pool+[movie],films:true).flatMap(\.programmes).allSatisfy(\.film))
        precondition(EditorialShelves.matchesChristmas(pool[0],programme([["id":"x","title":"Christmas Special","brands":[]]]).episodes[0]))
        precondition(!EditorialShelves.matchesChristmas(pool[0],programme([["id":"x","title":"Episode 1","brands":[]]]).episodes[0]))
        let collection=CollectionDestination(programmeID:"discover_123",collection:"christmas")
        precondition(CollectionDestination.parse(collection.pathValue)==collection)
        precondition(CollectionDestination.parse("plain-programme-id")==nil)
        precondition(CollectionDestination.parse("collection:unknown:123")==nil)
        let dayA=EditorialShelves.make(pool,films:false,year:2026,rotationDay:100)
        let dayARepeat=EditorialShelves.make(pool,films:false,year:2026,rotationDay:100)
        precondition(dayA.map(\.id)==dayARepeat.map(\.id),"Themes moved around during one day's browsing")
        precondition(dayA.first?.id=="personal","Rotation moved the personal shelf")
        let festiveA=programme([ep("Christmas Special","1",1),ep("Ordinary episode","1",2)],id:"festive-a")
        let festiveB=programme([ep("Xmas Treat","2",1),ep("Christmas Edition","2",2)],id:"festive-b")
        let episodeCards=EditorialShelves.christmasEpisodes([festiveA,festiveB])
        precondition(episodeCards.map(\.id)==["Christmas Special","Xmas Treat","Christmas Edition"],"Christmas cards selected unrelated episodes or lost interleaving")
        precondition(episodeCards[1].programme.id=="festive-b" && episodeCards[1].episode.id=="Xmas Treat","Christmas playback target drifted to the show's preferred episode")
        let familiar=(0..<4).map{programme([],id:"known-\($0)",title:"Known \($0)",poster:"https://images.example/p.jpg",brandID:"bbc")}
        let fresh=(0..<40).map{programme([],id:"new-\($0)",title:"New \($0)",poster:"https://images.example/p.jpg",favourite:false,recent:false,brandID:"bbc")}
        let discoveryA=EditorialShelves.make(familiar+fresh,films:false,rotationDay:100)
        let discoveryB=EditorialShelves.make(familiar+fresh,films:false,rotationDay:101)
        let bbcA=discoveryA.first{$0.id=="iplayer"}!,bbcB=discoveryB.first{$0.id=="iplayer"}!
        precondition(bbcA.programmes.filter{!$0.favourite && !$0.recent}.count>=6,"Provider themes did not introduce enough unseen programmes")
        precondition(bbcA.programmes.map(\.id) != bbcB.programmes.map(\.id),"Broader discoveries never changed")
        precondition(discoveryA.first!.programmes.map(\.id)==discoveryB.first!.programmes.map(\.id),"Discovery rotation shuffled the personal shelf")
        let preview=programme([],id:"preview",title:"Known 0",favourite:false,recent:false,brandID:"bbc")
        let deduped=EditorialShelves.make([preview]+familiar+fresh,films:false,rotationDay:100)
        precondition(!deduped.flatMap(\.programmes).contains{$0.id=="preview"},"An already-known programme was presented as a new provider discovery")
        let continuation=discoveryA.filter{$0.id.hasPrefix("explore-")}
        precondition(continuation.dropFirst().allSatisfy{$0.title.isEmpty},"Every continuation row received another generic heading")
        let card=programme([ep("Series 1: 1. Pilot","1",1)]).episodes[0]
        precondition(card.cardHeading(showSeries:true)=="Series 1: Episode 1")
        precondition(card.cardHeading(showSeries:false)=="Episode 1","Filtered and single-series views omit the series prefix")
        let technical=programme([["id":"e","title":"Episode 1","season":"1","episode_number":1,"duration_seconds":1740,"quality":"HD","brands":[]]]).episodes[0]
        precondition(technical.cardDetails=="29 Min • HD","Runtime/quality do not repeat the episode number")
        let episodeRoute=EpisodeDestination(programmeID:"show:qi",episodeID:"bbc:episode/6")
        precondition(EpisodeDestination.parse(episodeRoute.pathValue)==episodeRoute,"Episode selection survives navigation encoding")
        precondition(EpisodeDestination.parse("episode:invalid")==nil,"Malformed episode routes are rejected")
        print("Cinematic library checks passed: later episodes/seasons, watched editions, specials, films/live exclusion and backwards-compatible artwork")
    }
}
